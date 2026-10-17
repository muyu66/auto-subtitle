"""模型下载：faster-whisper（ModelScope）与 SenseVoice（HF 镜像）。

国内网络访问 Hugging Face 通常不稳定，而 ModelScope 的 CDN 速度更快、
无需登录。这里用标准库实现下载（支持断点续传和进度显示），避免额外依赖。
"""

from __future__ import annotations

import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

MODELSCOPE_REPOS = {
    "tiny": "pengzhendong/faster-whisper-tiny",
    "base": "pengzhendong/faster-whisper-base",
    "small": "pengzhendong/faster-whisper-small",
    "medium": "pengzhendong/faster-whisper-medium",
    "large-v3": "pengzhendong/faster-whisper-large-v3",
    "turbo": "pengzhendong/faster-whisper-large-v3-turbo",
}
IGNORED_FILES = {".gitattributes", "README.md", "configuration.json"}
_COMPLETE_MARKER = ".complete"
_USER_AGENT = "auto-subtitle/1.0"

# 中文专用语音模型 SenseVoice（sherpa-onnx 格式，int8 量化）。
# 文件大小用于下载完成后校验，避免半截文件被当成完整模型。
SENSEVOICE_REPO = (
    "csukuangfj/sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17"
)
SENSEVOICE_FILES = (
    ("model.int8.onnx", 239233841),
    ("tokens.txt", 315894),
)
SENSEVOICE_DIR_NAME = "sensevoice"


class ModelDownloadError(RuntimeError):
    pass


def canonical_model_name(name: str) -> str:
    from .asr import MODEL_ALIASES

    return MODEL_ALIASES.get(name, name)


def cache_root() -> Path:
    base = (
        os.environ.get("LOCALAPPDATA")
        or os.environ.get("XDG_CACHE_HOME")
        or os.path.expanduser("~/.cache")
    )
    root = Path(base) / "auto-subtitle" / "models"
    legacy = Path(base) / "video-quick-edit" / "models"
    if not root.exists() and legacy.exists():
        # 项目改名后沿用旧缓存，避免已下载的模型需要重新下载。
        try:
            root.parent.mkdir(parents=True, exist_ok=True)
            legacy.rename(root)
        except OSError:
            return legacy
    return root


def model_directory(name: str) -> Path:
    return cache_root() / canonical_model_name(name)


def is_model_ready(name: str) -> bool:
    directory = model_directory(name)
    return (directory / _COMPLETE_MARKER).exists() and (directory / "model.bin").is_file()


def _open(url: str, headers: dict | None = None, timeout: float = 60.0):
    request = urllib.request.Request(
        url,
        headers={"User-Agent": _USER_AGENT, **(headers or {})},
    )
    return urllib.request.urlopen(request, timeout=timeout)


def _list_files(repo: str) -> list[tuple[str, int]]:
    url = (
        f"https://www.modelscope.cn/api/v1/models/{repo}/repo/files"
        "?Revision=master&Root="
    )
    with _open(url, timeout=30.0) as response:
        payload = json.loads(response.read().decode("utf-8"))
    files: list[tuple[str, int]] = []
    for item in payload.get("Data", {}).get("Files", []):
        name = item.get("Name") or ""
        if not name or name in IGNORED_FILES or item.get("Type") != "blob":
            continue
        try:
            size = int(item.get("Size") or 0)
        except (TypeError, ValueError):
            size = 0
        files.append((name, size))
    if not any(name == "model.bin" for name, _ in files):
        raise ModelDownloadError(f"ModelScope 仓库 {repo} 中没有 model.bin")
    return files


def _format_size(num_bytes: float) -> str:
    if num_bytes >= 1024 ** 3:
        return f"{num_bytes / (1024 ** 3):.2f} GB"
    return f"{num_bytes / (1024 ** 2):.1f} MB"


def _progress_line(
    filename: str,
    downloaded: int,
    total: int,
    started: float,
) -> str:
    elapsed = max(time.monotonic() - started, 0.001)
    speed = downloaded / elapsed
    parts = [f"下载 {filename}"]
    if total > 0:
        parts.append(f"{downloaded / total * 100:5.1f}%")
        parts.append(f"{_format_size(downloaded)}/{_format_size(total)}")
        if speed > 0:
            remaining = max(total - downloaded, 0) / speed
            parts.append(f"剩余 {int(remaining // 60):02d}:{int(remaining % 60):02d}")
    else:
        parts.append(_format_size(downloaded))
    parts.append(f"{_format_size(speed)}/s")
    return "  ".join(parts)


def _download_once(
    url: str,
    part: Path,
    expected_size: int,
    filename: str,
) -> None:
    existing = part.stat().st_size if part.exists() else 0
    headers = {}
    if existing:
        headers["Range"] = f"bytes={existing}-"

    tty = sys.stdout.isatty()
    try:
        response = _open(url, headers=headers)
    except urllib.error.HTTPError as exc:
        # 断点文件已经完整，或服务器不支持 Range：从头下载
        if exc.code in (416, 200):
            if part.exists():
                part.unlink()
            existing = 0
            response = _open(url)
        else:
            raise

    with response:
        status = getattr(response, "status", 200)
        if status == 206 and existing:
            mode = "ab"
            downloaded = existing
            length = int(response.headers.get("Content-Length") or 0)
            total = existing + length if length else expected_size
        else:
            mode = "wb"
            downloaded = 0
            total = expected_size or int(response.headers.get("Content-Length") or 0)

        started = time.monotonic()
        last_report = 0.0
        with open(part, mode) as handle:
            while True:
                chunk = response.read(1024 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                downloaded += len(chunk)
                now = time.monotonic()
                if tty:
                    line = _progress_line(filename, downloaded, total, started)
                    print("\r" + line + " " * 6, end="", flush=True)
                elif now - last_report >= 5.0:
                    print(_progress_line(filename, downloaded, total, started), flush=True)
                    last_report = now

    if tty:
        print()
    if total > 0 and downloaded < total:
        raise ModelDownloadError(
            f"{filename} 下载不完整（{downloaded}/{total} 字节）"
        )
    if expected_size > 0 and downloaded != expected_size:
        raise ModelDownloadError(
            f"{filename} 大小不正确（{downloaded}，应为 {expected_size}）"
        )


def _download_file(url: str, target: Path, size: int, filename: str) -> None:
    part = target.with_name(target.name + ".part")
    if part.exists() and size > 0:
        current = part.stat().st_size
        if current == size:
            part.replace(target)
            return
        if current > size:
            part.unlink()

    last_error: Exception | None = None
    for attempt in range(1, 4):
        try:
            _download_once(url, part, size, filename)
            part.replace(target)
            return
        except (
            urllib.error.URLError,
            http.client.HTTPException,
            TimeoutError,
            OSError,
            ModelDownloadError,
        ) as exc:
            last_error = exc
            if attempt < 3:
                print(f"\n下载中断，正在重试（{attempt}/3）：{exc}", flush=True)
                time.sleep(2)
    raise ModelDownloadError(f"下载 {filename} 失败：{last_error}")


def download_model(name: str, log=print) -> Path:
    """下载模型到本地缓存，返回模型目录。已下载则直接返回。"""
    canonical = canonical_model_name(name)
    directory = model_directory(canonical)
    if is_model_ready(canonical):
        return directory

    repo = MODELSCOPE_REPOS.get(canonical)
    if not repo:
        raise ModelDownloadError(f"没有为模型 {name} 配置 ModelScope 下载源")

    directory.mkdir(parents=True, exist_ok=True)
    files = _list_files(repo)
    total_size = sum(size for _, size in files)
    log(f"正在从 ModelScope 下载模型 {canonical}（约 {_format_size(total_size)}）……")

    for filename, size in files:
        target = directory / filename
        if target.exists() and (size <= 0 or target.stat().st_size == size):
            continue
        url = (
            f"https://www.modelscope.cn/models/{repo}/resolve/master/"
            f"{urllib.parse.quote(filename)}"
        )
        _download_file(url, target, size, filename)

    marker = directory / _COMPLETE_MARKER
    marker.write_text(f"{repo}\n", encoding="utf-8")
    log(f"模型下载完成：{directory}")
    return directory


def sensevoice_directory() -> Path:
    return cache_root() / SENSEVOICE_DIR_NAME


def is_sensevoice_ready() -> bool:
    directory = sensevoice_directory()
    if not (directory / _COMPLETE_MARKER).is_file():
        return False
    return all(
        (directory / name).is_file()
        and (directory / name).stat().st_size == size
        for name, size in SENSEVOICE_FILES
    )


def download_sensevoice(log=print) -> Path:
    """下载 SenseVoice 中文模型到本地缓存，返回模型目录。"""
    directory = sensevoice_directory()
    if is_sensevoice_ready():
        return directory

    base = (os.environ.get("HF_ENDPOINT") or "https://hf-mirror.com").rstrip("/")
    directory.mkdir(parents=True, exist_ok=True)
    total = sum(size for _, size in SENSEVOICE_FILES)
    log(f"正在下载中文语音模型 SenseVoice（约 {_format_size(total)}）……")

    for filename, size in SENSEVOICE_FILES:
        target = directory / filename
        if target.is_file() and target.stat().st_size == size:
            continue
        url = (
            f"{base}/{SENSEVOICE_REPO}/resolve/main/"
            f"{urllib.parse.quote(filename)}"
        )
        _download_file(url, target, size, filename)

    marker = directory / _COMPLETE_MARKER
    marker.write_text(f"{SENSEVOICE_REPO}\n", encoding="utf-8")
    log(f"中文模型下载完成：{directory}")
    return directory

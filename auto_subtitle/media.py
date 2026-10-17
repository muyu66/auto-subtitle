"""媒体文件相关的工具：路径解析、ffmpeg 探测、音频提取。"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

VIDEO_EXTS = {
    ".mp4", ".mkv", ".mov", ".avi", ".flv", ".webm", ".wmv", ".m4v",
    ".mpg", ".mpeg", ".ts", ".m2ts", ".3gp", ".rmvb", ".rm", ".vob", ".ogv",
}
AUDIO_EXTS = {
    ".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".amr",
}
SUPPORTED_EXTS = VIDEO_EXTS | AUDIO_EXTS


class MediaError(RuntimeError):
    """媒体处理相关的用户可见错误。"""


def parse_dropped_paths(raw: str) -> list[str]:
    """解析从终端拖入的一行内容。

    Windows 终端拖入文件时会给含空格的路径加双引号；一次拖入多个文件时，
    会得到 ``"a.mp4" "b.mp4"`` 这样的形式。若整行没有引号，则按一个路径处理
    （允许路径本身含空格）。
    """
    raw = raw.strip()
    if not raw:
        return []

    # PowerShell 拖入时偶尔会带上前缀 &，这里一并去掉。
    raw = re.sub(r"^&\s+", "", raw)

    # 整个输入被单引号包住：一个路径
    if len(raw) >= 2 and raw[0] == "'" and raw[-1] == "'":
        return [raw[1:-1].strip()] if raw[1:-1].strip() else []

    # 存在双引号时，按「带引号的路径 + 空白分隔的路径」逐项解析。
    # 例如："C:\a b\one.mp4" C:\two.mp4
    if '"' in raw:
        token_pattern = re.compile(r'"([^"]*)"|([^\s"]+)')
        paths: list[str] = []
        for match in token_pattern.finditer(raw):
            value = (match.group(1) if match.group(1) is not None else match.group(2))
            value = (value or "").strip()
            if value and value != "&":
                paths.append(value)
        if paths:
            return paths

    # 没有引号时，整行视为一个路径（允许路径本身含空格）。
    return [raw]


def normalize_path(raw: str) -> Path:
    """展开环境变量和 ~，并去掉可能残留的引号。"""
    text = raw.strip().strip('"').strip("'")
    text = os.path.expandvars(text)
    text = os.path.expanduser(text)
    return Path(text)


def is_supported_media(path: Path) -> bool:
    return path.suffix.lower() in SUPPORTED_EXTS


def find_ffmpeg() -> str:
    exe = shutil.which("ffmpeg")
    if not exe:
        raise MediaError(
            "未找到 ffmpeg。请先安装 ffmpeg 并把它加入 PATH，然后重新打开终端。\n"
            "  安装方法（任选其一）：\n"
            "    1. 在管理员终端执行：winget install Gyan.FFmpeg\n"
            "    2. 到 https://www.gyan.dev/ffmpeg/builds/ 下载后把 bin 目录加入 PATH"
        )
    return exe


def find_ffprobe() -> str | None:
    return shutil.which("ffprobe")


def probe_duration(path: Path) -> float | None:
    """返回媒体时长（秒）；失败时返回 None。"""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return float(result.stdout.strip())
    except (ValueError, OSError, subprocess.SubprocessError):
        return None


def has_audio_stream(path: Path) -> bool | None:
    """检查是否有音频轨。无法判断时返回 None。"""
    ffprobe = find_ffprobe()
    if not ffprobe:
        return None
    try:
        result = subprocess.run(
            [
                ffprobe, "-v", "error",
                "-select_streams", "a:0",
                "-show_entries", "stream=codec_type",
                "-of", "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
        )
        return bool(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None


def extract_audio(ffmpeg: str, source: Path, target: Path) -> None:
    """从视频中提取 16kHz 单声道 PCM 音频（Whisper 需要的格式）。"""
    cmd = [
        ffmpeg,
        "-hide_banner",
        "-loglevel", "error",
        "-nostdin",
        "-y",
        "-i", str(source),
        "-vn",
        "-ac", "1",
        "-ar", "16000",
        "-c:a", "pcm_s16le",
        str(target),
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as exc:
        raise MediaError(f"调用 ffmpeg 失败：{exc}") from exc

    if result.returncode != 0:
        detail = (result.stderr or "").strip()
        if len(detail) > 1200:
            detail = detail[-1200:]
        raise MediaError(f"音频提取失败（ffmpeg 返回码 {result.returncode}）：\n{detail}")


def format_hms(seconds: float | None) -> str:
    """把秒数格式化为 H:MM:SS 或 MM:SS。"""
    if seconds is None or seconds < 0:
        return "--:--"
    total = int(seconds)
    hours, rem = divmod(total, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"


def format_duration_cn(seconds: float | None) -> str:
    """把秒数格式化为「1 分 20 秒」这样的中文描述。"""
    if seconds is None or seconds < 0:
        return "未知"
    seconds = int(round(seconds))
    if seconds < 60:
        return f"{seconds} 秒"
    minutes, secs = divmod(seconds, 60)
    if minutes < 60:
        return f"{minutes} 分 {secs} 秒"
    hours, minutes = divmod(minutes, 60)
    return f"{hours} 小时 {minutes} 分"

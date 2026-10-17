"""本地语音识别（faster-whisper）。"""

from __future__ import annotations

import os
import urllib.request
from pathlib import Path

DEFAULT_MODEL = "turbo"

# 名称 -> (Hugging Face 仓库, 大致下载大小)
MODELS: dict[str, tuple[str, str]] = {
    "tiny": ("Systran/faster-whisper-tiny", "约 75 MB"),
    "base": ("Systran/faster-whisper-base", "约 145 MB"),
    "small": ("Systran/faster-whisper-small", "约 480 MB"),
    "medium": ("Systran/faster-whisper-medium", "约 1.5 GB"),
    "large-v3": ("Systran/faster-whisper-large-v3", "约 3.1 GB"),
    "turbo": ("deepdml/faster-whisper-large-v3-turbo-ct2", "约 1.6 GB"),
}
MODEL_ALIASES = {
    "large": "large-v3",
    "large-v3-turbo": "turbo",
    "large-turbo": "turbo",
}

LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "yue": "粤语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "ru": "俄语",
    "pt": "葡萄牙语",
    "it": "意大利语",
}

DEFAULT_PROMPT = "以下是普通话的句子。"


class ASRError(RuntimeError):
    """语音识别相关的用户可见错误。"""


def resolve_model(name: str) -> str:
    """把简写转换成仓库名；本地目录或完整仓库名原样返回。"""
    if Path(name).expanduser().exists():
        return str(Path(name).expanduser())
    key = MODEL_ALIASES.get(name, name)
    repo = MODELS.get(key)
    return repo[0] if repo else name


def model_download_hint(name: str) -> str:
    key = MODEL_ALIASES.get(name, name)
    info = MODELS.get(key)
    if not info:
        return ""
    return f"（模型 {key}，{info[1]}）"


def _hf_reachable(timeout: float = 4.0) -> bool:
    """快速判断 huggingface.co 是否可访问。"""
    request = urllib.request.Request(
        "https://huggingface.co/api/models?limit=1",
        headers={"User-Agent": "auto-subtitle/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            response.read(1)
        return True
    except Exception:
        return False


def configure_hf_endpoint() -> str | None:
    """在无法直连 Hugging Face 时启用 hf-mirror.com 镜像。

    返回实际切换到的镜像地址；未切换时返回 None。
    用户显式设置了 HF_ENDPOINT 或 HF_HUB_OFFLINE 时不做任何改动。
    """
    existing = os.environ.get("HF_ENDPOINT")
    if existing:
        return existing if "hf-mirror" in existing.lower() else None
    if os.environ.get("HF_HUB_OFFLINE", "").strip() in ("1", "true", "True"):
        return None
    if _hf_reachable():
        return None

    mirror = "https://hf-mirror.com"
    os.environ["HF_ENDPOINT"] = mirror
    # Windows 上创建符号链接可能失败，禁用相关警告
    os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
    return mirror


def hf_model_cached(repo_id: str) -> bool:
    """检查 Hugging Face 缓存里是否已有完整模型。"""
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        hub = Path(hf_home) / "hub"
    else:
        xdg = os.environ.get("XDG_CACHE_HOME")
        base = Path(xdg) if xdg else Path.home() / ".cache"
        hub = base / "huggingface" / "hub"
    snapshots = hub / ("models--" + repo_id.replace("/", "--")) / "snapshots"
    if not snapshots.is_dir():
        return False
    return any((snapshot / "model.bin").is_file() for snapshot in snapshots.iterdir())


def _cuda_available() -> bool:
    try:
        import ctranslate2

        return ctranslate2.get_cuda_device_count() > 0
    except Exception:
        return False


class Transcriber:
    """懒加载的 faster-whisper 封装。"""

    def __init__(
        self,
        model: str = DEFAULT_MODEL,
        device: str = "auto",
        compute_type: str | None = None,
        threads: int = 0,
        model_source: str = "auto",
    ) -> None:
        self.model_name = model
        self.repo_id = resolve_model(model)
        self.device = device
        self.compute_type = compute_type
        self.threads = threads or min(8, os.cpu_count() or 4)
        self.model_source_pref = model_source
        self._model = None
        self._mirror: str | None = None
        self.model_source = "Hugging Face"

    @property
    def mirror(self) -> str | None:
        return self._mirror

    @property
    def is_loaded(self) -> bool:
        return self._model is not None

    def load(self) -> None:
        if self._model is not None:
            return

        # Windows 上通常无法为 Hugging Face 缓存创建符号链接，隐藏这条长警告。
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        # 国内镜像通常不支持 Xet 传输，启用 Xet 会导致下载卡住；改用普通 HTTP 下载。
        os.environ.setdefault("HF_HUB_DISABLE_XET", "1")
        self._mirror = configure_hf_endpoint()

        # 国内网络下 ModelScope 的下载速度通常明显更快，且模型文件与 HF 一致。
        from .model_store import MODELSCOPE_REPOS, canonical_model_name, download_model

        canonical = canonical_model_name(self.model_name)
        prefer_modelscope = (
            self.model_source_pref in ("auto", "modelscope")
            and canonical in MODELSCOPE_REPOS
            and (self.model_source_pref == "modelscope" or not hf_model_cached(self.repo_id))
        )
        if prefer_modelscope:
            try:
                local_dir = download_model(canonical)
                self.repo_id = str(local_dir)
                self.model_source = "ModelScope"
            except Exception as exc:
                print("提示：ModelScope 下载失败，改用 Hugging Face 继续下载。")
                print(f"      原因：{exc}")

        if self.device == "auto":
            self.device = "cuda" if _cuda_available() else "cpu"
        compute_type = self.compute_type or (
            "float16" if self.device == "cuda" else "int8"
        )

        try:
            from faster_whisper import WhisperModel
        except ImportError as exc:  # pragma: no cover - 安装问题
            raise ASRError(
                "未安装 faster-whisper。请先运行「安装依赖.bat」，"
                "或执行：pip install -r requirements.txt"
            ) from exc

        try:
            self._model = WhisperModel(
                self.repo_id,
                device=self.device,
                compute_type=compute_type,
                cpu_threads=self.threads,
                num_workers=1,
            )
        except Exception as exc:
            raise ASRError(
                "语音模型加载失败。请检查网络后重试，或改用更小的模型"
                "（例如 --model small）。\n"
                f"详细信息：{exc}"
            ) from exc

    def describe_device(self) -> str:
        compute = self.compute_type or (
            "float16" if self.device == "cuda" else "int8"
        )
        if self.device == "cpu":
            return f"CPU（{compute}，{self.threads} 线程）"
        return f"{self.device.upper()}（{compute}）"

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = None,
        beam_size: int = 5,
        vad_filter: bool = True,
        initial_prompt: str | None = DEFAULT_PROMPT,
        hotwords: str | None = None,
    ):
        """返回 (segments 生成器, info)。"""
        self.load()
        try:
            segments, info = self._model.transcribe(
                str(audio_path),
                language=language,
                beam_size=max(1, int(beam_size)),
                vad_filter=vad_filter,
                vad_parameters=(
                    {
                        "min_silence_duration_ms": 500,
                        "speech_pad_ms": 200,
                    }
                    if vad_filter
                    else None
                ),
                condition_on_previous_text=False,
                initial_prompt=initial_prompt or None,
                hotwords=hotwords or None,
                word_timestamps=False,
            )
        except Exception as exc:
            raise ASRError(f"语音识别失败：{exc}") from exc
        return segments, info


def language_display(info) -> str:
    code = getattr(info, "language", None) or "未知"
    name = LANGUAGE_NAMES.get(code, code)
    probability = getattr(info, "language_probability", None)
    if probability is None:
        return name
    return f"{name}（{code}，置信度 {probability * 100:.1f}%）"

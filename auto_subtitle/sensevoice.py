"""中文专用语音识别（SenseVoice + sherpa-onnx）。

Whisper 是通用多语种模型，对中文口语、背景音乐和专有名词往往不够稳。
SenseVoice 是专门针对中文（以及英/日/韩/粤语）训练的模型，
在嘈杂环境和口语场景下通常更准确，且自带标点。

这里使用 sherpa-onnx 的 int8 版本：
- 模型约 228 MB，下载一次后可离线使用；
- 用 Silero VAD 把长音频切成语义段，再逐段识别；
- 时间轴来自 VAD 分段，段内再由 subtitles.build_cues 按标点拆分。
"""

from __future__ import annotations

import os
import wave
from dataclasses import dataclass
from pathlib import Path

from .asr import ASRError
from .model_store import download_sensevoice

VAD_MODEL = Path(__file__).resolve().parent / "assets" / "silero_vad.onnx"
SUPPORTED_LANGUAGES = {"auto", "zh", "en", "ja", "ko", "yue"}
DEFAULT_LANGUAGE = "zh"


@dataclass
class SpeechSegment:
    start: float
    end: float
    text: str


@dataclass
class SenseVoiceInfo:
    language: str
    language_probability: float | None = None
    duration: float | None = None


def _meaningful(text: str) -> bool:
    """过滤只剩标点/空白，或只有一个字的噪声结果。"""
    return sum(1 for ch in text if ch.isalnum()) >= 2


class SenseVoiceTranscriber:
    """懒加载的 SenseVoice 封装。"""

    engine_name = "sensevoice"

    def __init__(
        self,
        threads: int = 0,
        language: str = DEFAULT_LANGUAGE,
        min_silence: float = 0.8,
        vad_threshold: float = 0.4,
        max_speech: float = 30.0,
    ) -> None:
        self.threads = threads or min(8, os.cpu_count() or 4)
        self.language = language or DEFAULT_LANGUAGE
        self.min_silence = min_silence
        self.vad_threshold = vad_threshold
        self.max_speech = max_speech
        self.model_source = "SenseVoice（sherpa-onnx）"
        self.mirror = None
        self._model_dir: Path | None = None
        self._recognizers: dict[str, object] = {}

    @property
    def is_loaded(self) -> bool:
        return self._model_dir is not None

    def load(self) -> None:
        if self._model_dir is not None:
            return

        try:
            import sherpa_onnx  # noqa: F401
        except ImportError as exc:  # pragma: no cover - 安装问题
            raise ASRError(
                "未安装 sherpa-onnx。请重新运行「安装依赖.bat」，"
                "或执行：pip install -r requirements.txt"
            ) from exc

        if not VAD_MODEL.is_file():
            raise ASRError(
                f"缺少静音检测模型：{VAD_MODEL}\n"
                "请重新解压完整的项目文件，或改用 --engine whisper。"
            )

        try:
            self._model_dir = download_sensevoice()
        except Exception as exc:
            raise ASRError(
                "中文语音模型下载失败。可以检查网络后重试，"
                "或改用 Whisper：--engine whisper。\n"
                f"详细信息：{exc}"
            ) from exc

    def _recognizer(self, language: str):
        """按语言缓存识别器；同一进程处理多语言文件时不必重复加载。"""
        key = language or "auto"
        if key not in self._recognizers:
            import sherpa_onnx

            self._recognizers[key] = sherpa_onnx.OfflineRecognizer.from_sense_voice(
                model=str(self._model_dir / "model.int8.onnx"),
                tokens=str(self._model_dir / "tokens.txt"),
                num_threads=self.threads,
                use_itn=True,
                language=key,
            )
        return self._recognizers[key]

    def _read_wav(self, audio_path: str | Path) -> tuple[object, int, float]:
        import numpy as np

        try:
            with wave.open(str(audio_path), "rb") as handle:
                channels = handle.getnchannels()
                width = handle.getsampwidth()
                sample_rate = handle.getframerate()
                frames = handle.readframes(handle.getnframes())
        except (OSError, EOFError) as exc:
            raise ASRError(f"读取音频失败：{exc}") from exc

        if channels != 1 or width != 2 or sample_rate != 16000:
            raise ASRError(
                "内部音频格式不正确（需要 16kHz 单声道 16 位 WAV），"
                "请重新运行程序。"
            )
        data = np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0
        duration = len(data) / sample_rate
        return data, sample_rate, duration

    def _vad_segments(self, data, sample_rate: int):
        import numpy as np
        import sherpa_onnx

        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(VAD_MODEL)
        config.silero_vad.threshold = self.vad_threshold
        config.silero_vad.min_silence_duration = self.min_silence
        config.silero_vad.min_speech_duration = 0.3
        config.silero_vad.max_speech_duration = self.max_speech
        config.sample_rate = sample_rate

        vad = sherpa_onnx.VoiceActivityDetector(
            config, buffer_size_in_seconds=120
        )

        def drain():
            while not vad.empty():
                segment = vad.front
                start = segment.start / sample_rate
                samples = np.array(segment.samples, dtype=np.float32)
                yield start, start + len(samples) / sample_rate
                vad.pop()

        chunk = 3200  # 0.2 秒
        for index in range(0, len(data), chunk):
            vad.accept_waveform(data[index:index + chunk])
            yield from drain()
        vad.flush()
        yield from drain()

    def transcribe(
        self,
        audio_path: str | Path,
        language: str | None = None,
        **_ignored,
    ):
        """返回 (segments 生成器, info)，与 Whisper 的调用方式保持一致。"""
        self.load()
        language = (language or self.language or DEFAULT_LANGUAGE).lower()
        if language == "auto":
            language = "auto"
        if language not in SUPPORTED_LANGUAGES:
            raise ASRError(
                f"SenseVoice 不支持语言 {language!r}，"
                "请改用 --engine whisper，或把语言设为 zh / auto。"
            )

        self._recognizer(language)  # 提前加载，错误尽早暴露
        data, sample_rate, duration = self._read_wav(audio_path)
        info = SenseVoiceInfo(language=language, duration=duration)

        def segments():
            import numpy as np

            recognizer = self._recognizer(language)
            padding = int(0.3 * sample_rate)
            for start, end in self._vad_segments(data, sample_rate):
                center = int(start * sample_rate)
                begin = max(0, center - padding)
                finish = min(len(data), int(end * sample_rate) + padding)
                samples = np.ascontiguousarray(data[begin:finish])
                if len(samples) == 0:
                    continue
                stream = recognizer.create_stream()
                stream.accept_waveform(sample_rate, samples)
                recognizer.decode_stream(stream)
                text = " ".join(stream.result.text.split())
                if text and _meaningful(text):
                    yield SpeechSegment(start=start, end=end, text=text)

        return segments(), info

    def describe_device(self) -> str:
        return f"CPU（SenseVoice int8，{self.threads} 线程）"

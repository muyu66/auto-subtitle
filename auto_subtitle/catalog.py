"""可选的语音识别模型列表（供交互式选择与 --list-models 使用）。"""

from __future__ import annotations

from dataclasses import dataclass

from .asr import DEFAULT_MODEL


@dataclass(frozen=True)
class ModelChoice:
    key: str
    engine: str
    title: str
    size: str
    description: str


MODEL_CHOICES: tuple[ModelChoice, ...] = (
    ModelChoice(
        key="sensevoice",
        engine="sensevoice",
        title="SenseVoice 中文专用",
        size="约 228 MB",
        description="中文口语更稳，速度快，自带标点",
    ),
    ModelChoice(
        key="turbo",
        engine="whisper",
        title="Whisper turbo",
        size="约 1.6 GB",
        description="多语种通用，句子连贯，CPU 速度较快",
    ),
    ModelChoice(
        key="large-v3",
        engine="whisper",
        title="Whisper large-v3",
        size="约 3.1 GB",
        description="准确率最高，CPU 上较慢",
    ),
    ModelChoice(
        key="medium",
        engine="whisper",
        title="Whisper medium",
        size="约 1.5 GB",
        description="精度和速度折中",
    ),
    ModelChoice(
        key="small",
        engine="whisper",
        title="Whisper small",
        size="约 480 MB",
        description="更快，适合长视频或配置较低的电脑",
    ),
    ModelChoice(
        key="base",
        engine="whisper",
        title="Whisper base",
        size="约 145 MB",
        description="只建议用于快速测试流程",
    ),
)

CUSTOM_LABEL = "其他 Whisper 模型（手动输入名称或本地目录）"


def current_choice_key(engine: str, model: str | None) -> str:
    """根据当前参数推断应高亮的模型。engine 为 auto 时使用 Whisper。"""
    if engine == "auto":
        engine = "whisper"
    if engine == "sensevoice":
        return "sensevoice"
    return (model or DEFAULT_MODEL).lower()


def current_choice_label(engine: str, model: str | None) -> str:
    key = current_choice_key(engine, model)
    for choice in MODEL_CHOICES:
        if choice.key == key:
            return choice.title
    return f"Whisper（{model or DEFAULT_MODEL}）"


def apply_choice(args, key: str, model: str | None = None) -> None:
    """把菜单选择写回参数对象。"""
    for choice in MODEL_CHOICES:
        if choice.key == key:
            args.engine = choice.engine
            args.model = choice.key if choice.engine == "whisper" else DEFAULT_MODEL
            return
    # 自定义 Whisper 模型名或本地目录
    args.engine = "whisper"
    args.model = model or key

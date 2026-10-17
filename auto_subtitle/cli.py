"""命令行入口与交互流程。"""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
import time
import unicodedata
from pathlib import Path

from . import __version__
from .asr import (
    DEFAULT_MODEL,
    DEFAULT_PROMPT,
    MODELS,
    Transcriber,
    language_display,
    model_download_hint,
)
from .catalog import (
    CUSTOM_LABEL,
    MODEL_CHOICES,
    apply_choice,
    current_choice_key,
    current_choice_label,
)
from .media import (
    MediaError,
    extract_audio,
    find_ffmpeg,
    format_duration_cn,
    format_hms,
    has_audio_stream,
    is_supported_media,
    normalize_path,
    parse_dropped_paths,
    probe_duration,
)
from .subtitles import (
    apply_replacements,
    build_cues,
    cues_to_srt,
    cues_to_text,
    parse_replacements,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-subtitle",
        description="把视频里的语音识别成字幕，并导出 SRT 文件。",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例：\n"
            "  运行.bat                         交互模式，拖入文件\n"
            "  运行.bat D:\\videos\\a.mp4          直接处理单个文件\n"
            "  运行.bat a.mp4 b.mp4 -o D:\\out    批量处理并指定输出目录\n"
            "  运行.bat a.mp4 --model small       使用更小更快的模型\n"
        ),
    )
    parser.add_argument("files", nargs="*", help="视频或音频文件路径；不填则进入交互模式")
    parser.add_argument(
        "-m", "--model", default=DEFAULT_MODEL,
        help=f"Whisper 语音模型：{' / '.join(MODELS)}，也可填仓库名或本地目录"
             f"（默认 {DEFAULT_MODEL}）",
    )
    parser.add_argument(
        "--engine", choices=["auto", "whisper", "sensevoice"], default="auto",
        help="识别引擎：auto（默认，等同 whisper）、whisper 或 sensevoice",
    )
    parser.add_argument(
        "--model-source", choices=["auto", "modelscope", "hf"], default="auto",
        help="Whisper 模型下载源：auto（默认，优先 ModelScope）、modelscope 或 hf",
    )
    parser.add_argument(
        "-l", "--language", default=None,
        help="语言代码，如 zh、en；默认自动检测（中文为主时通常无需指定）",
    )
    parser.add_argument(
        "-o", "--output-dir", default=None, help="字幕输出目录（默认与视频同目录）",
    )
    parser.add_argument(
        "-f", "--format", choices=["srt", "txt", "both"], default="srt",
        help="输出格式：srt（默认）、txt 或 both",
    )
    parser.add_argument(
        "--max-chars", type=int, default=30,
        help="每条字幕最大字符数，默认 30",
    )
    parser.add_argument(
        "--beam-size", type=int, default=5,
        help="识别束搜索宽度，越大越准但越慢，默认 5",
    )
    parser.add_argument(
        "--threads", type=int, default=0,
        help="CPU 线程数，默认自动（最多 8）",
    )
    parser.add_argument(
        "--device", choices=["auto", "cpu", "cuda"], default="auto",
        help="计算设备，默认自动检测",
    )
    parser.add_argument(
        "--compute-type", default=None,
        help="计算精度，如 int8、float16、float32；默认 CPU 用 int8，GPU 用 float16",
    )
    parser.add_argument(
        "--no-vad", action="store_true",
        help="关闭静音检测（默认开启，可减少空白段和幻觉）",
    )
    parser.add_argument(
        "--hotwords", default=None,
        help="热词，用空格或逗号分隔，例如游戏名、角色名、武器名",
    )
    parser.add_argument(
        "--replace", default=None,
        help="识别结果替换，格式：错词=正确词,错词2=正确词2",
    )
    parser.add_argument(
        "--initial-prompt", default=None,
        help="识别引导提示，可用于固定专有名词或语言风格",
    )
    parser.add_argument(
        "--no-prompt", action="store_true",
        help="不使用中文引导提示（用于纯英文等场景）",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="输出文件已存在时直接覆盖（默认自动改名，不覆盖已有文件）",
    )
    parser.add_argument(
        "--list-models", action="store_true", help="列出可选模型后退出",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return parser


def print_models() -> None:
    print("可选识别模型（首次使用会自动下载）：")
    for index, choice in enumerate(MODEL_CHOICES, start=1):
        recommended = "  ← 中文推荐" if choice.key == "sensevoice" else ""
        print(
            f"  {index}. {_fit_to_width(choice.title, 22)}"
            f" {choice.size:<9} {choice.description}{recommended}"
        )
    print(f"  {len(MODEL_CHOICES) + 1}. {CUSTOM_LABEL}")
    print("\n说明：SenseVoice 中文口语更稳、速度最快；turbo 句子更连贯、多语种通用；")
    print("      large-v3 最准但 CPU 上较慢；small 适合长视频或配置较低的电脑。")
    print("      也可以用 --model 指定任意 faster-whisper 格式的仓库名或本地目录。")
    print("\n交互启动时先用序号选择模型；识别过程中输入 m 可随时切换。")


def _print_model_menu(args: argparse.Namespace) -> None:
    current = current_choice_key(args.engine, args.model)
    print()
    print("请选择识别模型（直接回车使用当前模型）：")
    for index, choice in enumerate(MODEL_CHOICES, start=1):
        mark = "→" if choice.key == current else " "
        print(
            f" {mark} {index}. {_fit_to_width(choice.title, 22)}"
            f" {choice.size:<9} {choice.description}"
        )
    print(f"   {len(MODEL_CHOICES) + 1}. {CUSTOM_LABEL}")
    print(f"   当前：{current_choice_label(args.engine, args.model)}")


def choose_model(args: argparse.Namespace) -> None:
    """交互式选择模型，结果写回 args.engine / args.model。"""
    while True:
        _print_model_menu(args)
        current = current_choice_label(args.engine, args.model)
        try:
            raw = input(f"选择序号 [回车={current}]：").strip()
        except EOFError:
            print()
            return
        if not raw:
            return
        if raw.lower() in ("q", "quit", "exit"):
            print("再见。")
            raise SystemExit(0)
        if raw.isdigit():
            index = int(raw)
            if 1 <= index <= len(MODEL_CHOICES):
                apply_choice(args, MODEL_CHOICES[index - 1].key)
                print(f"已选择：{current_choice_label(args.engine, args.model)}")
                return
            if index == len(MODEL_CHOICES) + 1:
                try:
                    name = input(
                        "请输入 Whisper 模型名称或本地模型目录："
                    ).strip()
                except EOFError:
                    print()
                    return
                if name:
                    apply_choice(args, name, model=name)
                    print(
                        f"已选择：{current_choice_label(args.engine, args.model)}"
                    )
                    return
                continue
        print("请输入列表中的序号。")


def create_transcriber(args: argparse.Namespace):
    """按当前参数创建识别器（模型按需加载，此时不会开始下载）。"""
    engine = args.engine
    if engine == "auto":
        engine = "whisper"

    if engine == "sensevoice":
        from .sensevoice import SenseVoiceTranscriber

        if args.model != DEFAULT_MODEL:
            print("提示：SenseVoice 引擎不使用 --model 参数，已忽略。")
        return SenseVoiceTranscriber(
            threads=args.threads,
            language=args.language or "zh",
        )

    return Transcriber(
        model=args.model,
        device=args.device,
        compute_type=args.compute_type,
        threads=args.threads,
        model_source=args.model_source,
    )


def print_banner() -> None:
    line = "=" * 62
    print(line)
    print("  auto-subtitle  视频字幕生成工具  v" + __version__)
    print("  视频 → 提取音频 → 本地语音识别 → 导出 SRT 字幕")
    print(line)
    print("提示：把视频/音频文件直接拖到本窗口，按回车开始。")
    print("      可以一次拖入多个文件；输入 m 切换识别模型，输入 q 退出。")


def _display_width(text: str) -> int:
    return sum(
        2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        for ch in text
    )


def _fit_to_width(text: str, limit: int) -> str:
    """按终端显示宽度截断并用空格补齐，避免中文导致换行。"""
    width = _display_width(text)
    if width <= limit:
        return text + " " * (limit - width)

    kept: list[str] = []
    kept_width = 0
    for ch in text:
        ch_width = 2 if unicodedata.east_asian_width(ch) in ("W", "F") else 1
        if kept_width + ch_width > limit - 1:
            break
        kept.append(ch)
        kept_width += ch_width
    return "".join(kept) + "…" + " " * max(0, limit - kept_width - 1)


class ProgressReporter:
    """识别进度显示（终端里原地刷新，重定向时逐行输出）。"""

    def __init__(self, total_seconds: float | None) -> None:
        self.total = total_seconds if total_seconds and total_seconds > 0 else None
        self.tty = sys.stdout.isatty()
        self.width = shutil.get_terminal_size((100, 20)).columns
        self.started = time.monotonic()

    def update(self, processed: float, text: str) -> None:
        processed = max(0.0, float(processed))
        elapsed = time.monotonic() - self.started

        if self.total:
            ratio = min(processed / self.total, 1.0)
            bar_width = 16
            filled = int(ratio * bar_width)
            bar = "#" * filled + "-" * (bar_width - filled)
            if processed > 0.5 and elapsed > 0.5:
                eta = elapsed * max(self.total - processed, 0.0) / processed
                eta_text = format_hms(eta)
            else:
                eta_text = "--:--"
            head = (
                f"[{bar}] {ratio * 100:5.1f}%  "
                f"{format_hms(processed)}/{format_hms(self.total)}  "
                f"剩余约 {eta_text}"
            )
        else:
            head = f"[已识别 {format_hms(processed)}]"

        preview = " ".join(str(text).split())
        if len(preview) > 26:
            preview = preview[:25] + "…"
        line = f"{head}  {preview}"

        if self.tty:
            print("\r" + _fit_to_width(line, self.width - 1), end="", flush=True)
        else:
            print(line, flush=True)

    def close(self) -> None:
        if self.tty:
            print()


def _output_stem(
    source: Path,
    output_dir: str | None,
    suffixes: list[str],
    overwrite: bool,
) -> tuple[Path, str]:
    """确定输出目录和文件名主干；避免覆盖已有文件。"""
    directory = Path(output_dir).expanduser() if output_dir else source.parent
    directory.mkdir(parents=True, exist_ok=True)
    base = source.stem

    if overwrite:
        return directory, base

    def is_free(stem: str) -> bool:
        return all(not (directory / f"{stem}{suffix}").exists() for suffix in suffixes)

    if is_free(base):
        return directory, base
    index = 1
    while not is_free(f"{base}.{index}"):
        index += 1
    return directory, f"{base}.{index}"


def _write_outputs(
    source: Path,
    cues: list,
    args: argparse.Namespace,
) -> list[Path]:
    suffixes: list[str] = []
    if args.format in ("srt", "both"):
        suffixes.append(".srt")
    if args.format in ("txt", "both"):
        suffixes.append(".txt")

    directory, stem = _output_stem(source, args.output_dir, suffixes, args.overwrite)
    written: list[Path] = []

    if args.format in ("srt", "both"):
        path = directory / f"{stem}.srt"
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(cues_to_srt(cues))
        written.append(path)

    if args.format in ("txt", "both"):
        path = directory / f"{stem}.txt"
        with open(path, "w", encoding="utf-8", newline="\r\n") as handle:
            handle.write(cues_to_text(cues))
        written.append(path)

    return written


def process_file(
    raw_path: str,
    args: argparse.Namespace,
    transcriber: Transcriber,
) -> bool:
    """处理一个文件。成功返回 True。"""
    source = normalize_path(raw_path)
    print()
    print("-" * 62)
    print(f"处理文件：{source}")

    if not source.exists():
        print("错误：文件不存在，请检查路径是否正确。")
        return False
    if not source.is_file():
        print("错误：这不是一个文件。")
        return False
    if not is_supported_media(source):
        print(f"提示：扩展名 {source.suffix or '（无）'} 不常见，仍会尝试用 ffmpeg 读取。")

    try:
        ffmpeg = find_ffmpeg()
    except MediaError as exc:
        print(f"错误：{exc}")
        return False

    audio_ok = has_audio_stream(source)
    if audio_ok is False:
        print("错误：该文件没有音频轨道，无法生成字幕。")
        return False

    duration = probe_duration(source)
    if duration:
        print(f"媒体时长：{format_hms(duration)}")

    language = args.language
    if language and language.lower() == "auto":
        language = None
    if language:
        # 接受 zh-CN / en_US 这类写法
        language = language.split("-")[0].split("_")[0].lower()

    if args.no_prompt:
        initial_prompt = None
    elif args.initial_prompt is not None:
        initial_prompt = args.initial_prompt
    elif language in (None, "zh"):
        initial_prompt = DEFAULT_PROMPT
    else:
        initial_prompt = None

    try:
        with tempfile.TemporaryDirectory(prefix="vqe-") as temp_dir:
            wav_path = Path(temp_dir) / "audio.wav"
            print("正在提取音频……", end="", flush=True)
            started = time.monotonic()
            extract_audio(ffmpeg, source, wav_path)
            print(f" 完成（{format_duration_cn(time.monotonic() - started)}）")

            is_sensevoice = getattr(transcriber, "engine_name", "") == "sensevoice"
            if is_sensevoice:
                print("正在加载中文语音模型：SenseVoice（约 228 MB，首次自动下载）")
            else:
                print(
                    "正在加载语音模型："
                    f"{args.model}{model_download_hint(args.model)}"
                )
            if not transcriber.is_loaded:
                print("模型下载一次后即可离线使用。")
                if not is_sensevoice:
                    print("如果下载太慢，可按 Ctrl+C 退出后换用更小的模型："
                          "运行.bat --model small")
            transcriber.load()
            print(f"模型来源：{transcriber.model_source}")
            if not is_sensevoice and transcriber.mirror and (
                transcriber.model_source != "ModelScope"
            ):
                print(f"提示：Hugging Face 直连不可用，已使用镜像 {transcriber.mirror}")
            print(f"运行设备：{transcriber.describe_device()}")

            print("正在识别语音……")
            segments, info = transcriber.transcribe(
                wav_path,
                language=language,
                beam_size=args.beam_size,
                vad_filter=not args.no_vad,
                initial_prompt=initial_prompt,
                hotwords=args.hotwords,
            )
            print(f"识别语言：{language_display(info)}")

            total = duration or getattr(info, "duration", None)
            reporter = ProgressReporter(total)
            started = time.monotonic()
            collected = []
            try:
                for segment in segments:
                    collected.append(segment)
                    reporter.update(segment.end, segment.text)
            finally:
                reporter.close()
            asr_elapsed = time.monotonic() - started
            print(f"语音识别完成，共 {len(collected)} 个片段，"
                  f"耗时 {format_duration_cn(asr_elapsed)}")

        cues = build_cues(collected, max_chars=args.max_chars)
        cues = apply_replacements(
            cues, parse_replacements(getattr(args, "replace", None))
        )
        if not cues:
            print("未识别到有效语音内容，没有生成字幕文件。")
            return False

        written = _write_outputs(source, cues, args)

    except MediaError as exc:
        print(f"错误：{exc}")
        return False
    except Exception as exc:  # 模型加载/识别等
        print(f"错误：{exc}")
        return False

    print(f"完成！共 {len(cues)} 条字幕。")
    for path in written:
        print(f"输出：{path}")
    return True


def interactive_loop(args: argparse.Namespace) -> int:
    print_banner()
    transcriber = None
    while True:
        if transcriber is None:
            choose_model(args)
            transcriber = create_transcriber(args)
        try:
            raw = input(
                "\n请拖入文件（可多个），按回车开始；"
                "输入 m 切换模型，输入 q 退出：\n> "
            )
        except EOFError:
            print()
            return 0
        except KeyboardInterrupt:
            print("\n已退出。")
            return 0

        command = raw.strip().lower()
        if command in ("q", "quit", "exit"):
            print("再见。")
            return 0
        if command == "m":
            transcriber = None
            continue

        paths = parse_dropped_paths(raw)
        if not paths:
            continue

        for raw_path in paths:
            try:
                process_file(raw_path, args, transcriber)
            except KeyboardInterrupt:
                print("\n已中断当前文件。")
                raise
            except Exception as exc:
                print(f"错误：{exc}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.list_models:
        print_models()
        return 0

    if args.max_chars < 8:
        args.max_chars = 8
    if args.beam_size < 1:
        args.beam_size = 1

    try:
        if args.files:
            transcriber = create_transcriber(args)
            failures = 0
            for raw_path in args.files:
                if not process_file(raw_path, args, transcriber):
                    failures += 1
            return 1 if failures else 0
        return interactive_loop(args)
    except KeyboardInterrupt:
        print("\n已取消。")
        return 130

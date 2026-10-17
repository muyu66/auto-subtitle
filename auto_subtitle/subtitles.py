"""把 Whisper 识别片段整理成适合观看的字幕条目，并导出 SRT。"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

SENTENCE_END = "。！？!?…"
CLAUSE_END = "，,、；;：:"
CLOSERS = "”’\"』」）)】》〉】"
OPENERS = "“‘\"（(【《〈「『"

_CJK_RE = re.compile(r"[㐀-䶿一-鿿぀-ヿ가-힯]")
_VERBAL_RE = re.compile(
    r"[A-Za-z0-9㐀-䶿一-鿿぀-ヿ가-힯]"
)
_HAN_RANGE = "㐀-䶿一-鿿"


def clean_text(text: str) -> str:
    """合并空白，并去掉中文字符之间多余的空格（保留英文词间空格）。"""
    text = " ".join(str(text).split())
    text = re.sub(rf"(?<=[{_HAN_RANGE}])\s+(?=[{_HAN_RANGE}])", "", text)
    text = re.sub(rf"(?<=[{_HAN_RANGE}])\s+(?=[，。！？；：、）】》」』])", "", text)
    text = re.sub(rf"(?<=[（【《「『])\s+(?=[{_HAN_RANGE}])", "", text)
    return text.strip()


@dataclass
class Cue:
    """一条字幕。"""

    start: float
    end: float
    text: str


def parse_replacements(spec: str | None) -> dict[str, str]:
    """解析 ``错词=正确词,错词2=正确词2`` 形式的替换表。"""
    if not spec:
        return {}
    result: dict[str, str] = {}
    for item in re.split(r"[,，;；\n]+", spec):
        item = item.strip()
        if not item or "=" not in item:
            continue
        wrong, right = item.split("=", 1)
        wrong = wrong.strip().strip("\"'")
        right = right.strip().strip("\"'")
        if wrong:
            result[wrong] = right
    return result


def apply_replacements(
    cues: list[Cue], replacements: dict[str, str]
) -> list[Cue]:
    """按用户词表修正识别结果（例如把常错的人名/术语替换掉）。"""
    if not replacements:
        return cues
    for cue in cues:
        text = cue.text
        for wrong, right in replacements.items():
            text = text.replace(wrong, right)
        cue.text = text
    return cues


def _split_after(text: str, marks: str) -> list[str]:
    """在指定标点之后切分，并保留标点；右引号/右括号跟随前一段。"""
    if not text:
        return []
    parts = re.split(rf"(?<=[{re.escape(marks)}])", text)
    merged: list[str] = []
    for part in parts:
        if not part:
            continue
        # 例：他说：“你好。”然后…… 切分后 ” 会落到下一段，把它挪回上一段。
        while part and merged and part[0] in CLOSERS:
            merged[-1] += part[0]
            part = part[1:]
        if part:
            merged.append(part)
    return merged


def _hard_wrap(text: str, max_chars: int) -> list[str]:
    """没有可用标点时按长度硬切，尽量在空格处断开。"""
    pieces: list[str] = []
    remaining = text
    while len(remaining) > max_chars:
        cut = max_chars
        # 不把左引号/左括号留在行尾
        while cut > 1 and remaining[cut - 1] in OPENERS:
            cut -= 1
        # 英文优先在空格处断开，避免把单词劈开
        lower_bound = max(1, int(max_chars * 0.6))
        space = remaining.rfind(" ", lower_bound, max_chars + 1)
        if space > 0:
            pieces.append(remaining[:space].rstrip())
            remaining = remaining[space + 1:].lstrip()
        else:
            pieces.append(remaining[:cut])
            remaining = remaining[cut:]
    if remaining:
        pieces.append(remaining)
    return [p for p in pieces if p]


def _split_long(text: str, max_chars: int) -> list[str]:
    text = text.strip()
    if not text:
        return []
    if len(text) <= max_chars:
        return [text]

    clauses = _split_after(text, CLAUSE_END)
    if len(clauses) > 1:
        result: list[str] = []
        for clause in clauses:
            result.extend(_split_long(clause, max_chars))
        return result
    return _hard_wrap(text, max_chars)


def _weight(text: str) -> float:
    """估算朗读这段文字所需时间的权重（中文按字，英文按字母约半权重）。"""
    weight = 0.0
    for ch in text:
        if _CJK_RE.match(ch) or ch.isdigit():
            weight += 1.0
        elif ch.isalpha() or ch.isalnum():
            weight += 0.5
    return max(weight, 1.0)


def build_cues(segments: Iterable, max_chars: int = 30) -> list[Cue]:
    """把识别片段重新切分：优先按句子/逗号断句，再按长度限制切分。"""
    max_chars = max(8, int(max_chars))
    raw_cues: list[Cue] = []

    for seg in segments:
        text = clean_text(seg.text)
        if not _VERBAL_RE.search(text):
            continue

        start = max(0.0, float(seg.start))
        end = float(seg.end)
        if end <= start:
            end = start + 0.3

        pieces: list[str] = []
        for sentence in _split_after(text, SENTENCE_END):
            pieces.extend(_split_long(sentence, max_chars))
        pieces = [p.strip() for p in pieces if p.strip()]
        if not pieces:
            continue

        weights = [_weight(p) for p in pieces]
        total_weight = sum(weights) or float(len(pieces))
        duration = end - start
        acc = 0.0
        for index, (piece, weight) in enumerate(zip(pieces, weights)):
            piece_start = start + duration * acc / total_weight
            acc += weight
            if index == len(pieces) - 1:
                piece_end = end
            else:
                piece_end = start + duration * acc / total_weight
            raw_cues.append(Cue(piece_start, piece_end, piece))

    return _normalize(raw_cues)


def _normalize(cues: list[Cue]) -> list[Cue]:
    """保证时间单调、不重叠，并避免零时长字幕。"""
    result: list[Cue] = []
    previous_end = 0.0
    for cue in cues:
        start = max(cue.start, previous_end)
        end = max(cue.end, start + 0.05)
        result.append(Cue(start, end, cue.text))
        previous_end = end
    return result


def format_timestamp(seconds: float) -> str:
    """SRT 时间戳：HH:MM:SS,mmm。"""
    total_ms = max(0, int(round(float(seconds) * 1000)))
    hours, rem = divmod(total_ms, 3_600_000)
    minutes, rem = divmod(rem, 60_000)
    secs, millis = divmod(rem, 1000)
    return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


def cues_to_srt(cues: Iterable[Cue]) -> str:
    blocks = [
        f"{index}\n{format_timestamp(cue.start)} --> {format_timestamp(cue.end)}\n{cue.text}"
        for index, cue in enumerate(cues, start=1)
    ]
    return "\n\n".join(blocks) + ("\n" if blocks else "")


def cues_to_text(cues: Iterable[Cue]) -> str:
    lines = [cue.text for cue in cues if cue.text.strip()]
    return "\n".join(lines) + ("\n" if lines else "")

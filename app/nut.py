from __future__ import annotations

import re
from dataclasses import dataclass


NON_ASCII = re.compile(r"[^\x00-\x7f]")
CALL_BEFORE = re.compile(r"([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\([^()]*$")
SPEAKER = re.compile(r"\bIMC_[A-Za-z0-9_]+\b")
VOICE = re.compile(r'"([^"\\]*(?:\\.[^"\\]*)*)"')


class NutError(ValueError):
    pass


@dataclass(frozen=True)
class StringSpan:
    start: int
    end: int
    original: str
    ordinal: int
    line: int
    context: str


def scan(text: str) -> list[StringSpan]:
    """Return Japanese raw strings outside comments and other literals."""

    spans: list[StringSpan] = []
    position = 0
    ordinal = 0
    length = len(text)
    while position < length:
        if text.startswith("//", position):
            newline = text.find("\n", position + 2)
            position = length if newline < 0 else newline + 1
            continue
        if text.startswith("/*", position):
            end = text.find("*/", position + 2)
            if end < 0:
                raise NutError(f"Unterminated block comment at offset {position}")
            position = end + 2
            continue
        if text.startswith('@"', position):
            content_start = position + 2
            content_end = _quoted_end(text, content_start, '"', allow_newline=True)
            original = text[content_start:content_end]
            ordinal += 1
            if NON_ASCII.search(original) and original.strip(" \t\r\n\u3000"):
                line = text.count("\n", 0, content_start) + 1
                spans.append(
                    StringSpan(
                        start=content_start,
                        end=content_end,
                        original=original,
                        ordinal=ordinal,
                        line=line,
                        context=_context(text, content_start, content_end, line),
                    )
                )
            position = content_end + 1
            continue
        if text[position] in {'"', "'"}:
            end = _quoted_end(text, position + 1, text[position], allow_newline=False)
            position = end + 1
            continue
        position += 1
    return spans


def replace(text: str, spans: list[StringSpan], translations: dict[int, str]) -> str:
    result = text
    for span in reversed(spans):
        translation = translations.get(span.ordinal, "")
        if not translation or translation == span.original:
            continue
        rendered = translation.replace("\r\n", "\n").replace("\r", "\n").replace("\n", r"\n")
        rendered = re.sub(r'(?<!\\)"', r'\\"', rendered)
        result = result[: span.start] + rendered + result[span.end :]
    scan(result)
    return result


def _quoted_end(text: str, position: int, quote: str, *, allow_newline: bool) -> int:
    while position < len(text):
        char = text[position]
        if char == "\\":
            position += 2
            continue
        if char == quote:
            return position
        if char in "\r\n" and not allow_newline:
            return position
        position += 1
    raise NutError(f"Unterminated {quote} string")


def _context(text: str, start: int, end: int, line: int) -> str:
    line_start = text.rfind("\n", 0, start) + 1
    line_end = text.find("\n", end)
    if line_end < 0:
        line_end = len(text)
    before = text[line_start:start]
    whole_line = text[line_start:line_end]
    after = text[end + 1 : line_end]
    details = [f"Line: {line}"]
    call = CALL_BEFORE.search(before)
    if call:
        details.append(f"Call: {call.group(1)}")
    speaker = SPEAKER.search(whole_line)
    if speaker:
        details.append(f"Speaker: {speaker.group(0)}")
    voice = VOICE.search(after)
    if voice:
        details.append(f"Voice: {voice.group(1)}")
    return "\n".join(details)

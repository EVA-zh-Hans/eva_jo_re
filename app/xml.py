from __future__ import annotations

import html
import re
import xml.etree.ElementTree as element_tree
from dataclasses import dataclass


NON_ASCII = re.compile(r"[^\x00-\x7f]")
TAG_NAME = re.compile(r"<\s*/?\s*([:\w.-]+)")
ATTRIBUTE = re.compile(r"([:\w.-]+)\s*=\s*([\"'])(.*?)\2", re.DOTALL)


class XmlError(ValueError):
    pass


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int
    original: str
    ordinal: int
    line: int
    context: str
    kind: str
    quote: str | None = None


def scan(text: str) -> list[TextSpan]:
    spans: list[TextSpan] = []
    position = 0
    ordinal = 0
    while position < len(text):
        opening = text.find("<", position)
        if opening < 0:
            ordinal = _append_text(text, position, len(text), spans, ordinal)
            break
        ordinal = _append_text(text, position, opening, spans, ordinal)
        if text.startswith("<!--", opening):
            standard_end = text.find("-->", opening + 4)
            game_end = text.find("->", opening + 4)
            candidates = [value for value in (standard_end, game_end) if value >= 0]
            if not candidates:
                break
            marker_start = min(candidates)
            end = marker_start + (3 if marker_start == standard_end else 2)
            position = end
            continue
        if text.startswith("<![CDATA[", opening):
            start = opening + 9
            end = _require_end(text, "]]>", start)
            raw = text[start:end]
            ordinal += 1
            if NON_ASCII.search(raw) and raw.strip(" \t\r\n\u3000"):
                line = text.count("\n", 0, start) + 1
                spans.append(TextSpan(start, end, raw, ordinal, line, f"Line: {line}\nCDATA", "cdata"))
            position = end + 3
            continue
        if text.startswith("<?", opening):
            position = _require_end(text, "?>", opening + 2) + 2
            continue
        end = _tag_end(text, opening + 1)
        tag_source = text[opening : end + 1]
        if not tag_source.startswith(("</", "<!")):
            tag_match = TAG_NAME.match(tag_source)
            tag = tag_match.group(1) if tag_match else "unknown"
            for match in ATTRIBUTE.finditer(tag_source):
                ordinal += 1
                raw = match.group(3)
                logical = html.unescape(raw)
                if not NON_ASCII.search(logical) or not logical.strip(" \t\r\n\u3000"):
                    continue
                start = opening + match.start(3)
                finish = opening + match.end(3)
                line = text.count("\n", 0, start) + 1
                attribute = match.group(1)
                spans.append(
                    TextSpan(
                        start,
                        finish,
                        logical,
                        ordinal,
                        line,
                        f"Line: {line}\nElement: {tag}\nAttribute: {attribute}",
                        "attribute",
                        match.group(2),
                    )
                )
        position = end + 1
    return spans


def replace(text: str, spans: list[TextSpan], translations: dict[int, str]) -> str:
    result = text
    for span in reversed(spans):
        translation = translations.get(span.ordinal, "")
        if not translation or translation == span.original:
            continue
        if span.kind == "cdata":
            if "]]>" in translation:
                raise XmlError("CDATA translation contains ]]> terminator")
            rendered = translation
        else:
            rendered = html.escape(translation, quote=span.kind == "attribute")
        result = result[: span.start] + rendered + result[span.end :]
    return result


def _append_text(
    source: str,
    start: int,
    end: int,
    spans: list[TextSpan],
    ordinal: int,
) -> int:
    raw = source[start:end]
    logical = html.unescape(raw)
    if raw:
        ordinal += 1
    if NON_ASCII.search(logical) and logical.strip(" \t\r\n\u3000"):
        line = source.count("\n", 0, start) + 1
        spans.append(TextSpan(start, end, logical, ordinal, line, f"Line: {line}\nText node", "text"))
    return ordinal


def _tag_end(text: str, position: int) -> int:
    quote = None
    while position < len(text):
        char = text[position]
        if quote:
            if char == quote:
                quote = None
        elif char in {'"', "'"}:
            quote = char
        elif char == ">":
            return position
        position += 1
    raise XmlError("Unterminated XML tag")


def _require_end(text: str, marker: str, position: int) -> int:
    end = text.find(marker, position)
    if end < 0:
        raise XmlError(f"Unterminated XML section: expected {marker}")
    return end


def validation_error(text: str) -> str | None:
    try:
        element_tree.fromstring(text)
    except element_tree.ParseError as exc:
        return str(exc)
    return None

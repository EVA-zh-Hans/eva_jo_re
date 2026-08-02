from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping


class EncodingError(UnicodeError):
    pass


def is_game_safe_cp932(char: str) -> bool:
    """Return whether one character uses a byte sequence accepted by the game."""
    try:
        encoded = char.encode("cp932", errors="strict")
    except UnicodeEncodeError:
        return False
    if len(encoded) == 1:
        return True
    return len(encoded) == 2 and (
        0x81 <= encoded[0] <= 0x9F or 0xE0 <= encoded[0] <= 0xEA
    )


def encode_game_text(
    text: str,
    substitutions: Mapping[str, str] | None = None,
) -> bytes:
    substituted = (
        "".join(substitutions.get(char, char) for char in text)
        if substitutions
        else text
    )
    output = bytearray()
    for index, char in enumerate(substituted):
        try:
            encoded = char.encode("cp932", errors="strict")
        except UnicodeEncodeError as exc:
            raise EncodingError(
                f"Cannot encode {char!r} as CP932 at character {index}"
            ) from exc
        if not is_game_safe_cp932(char):
            raise EncodingError(
                f"Unsafe CP932 byte sequence {encoded.hex().upper()} for {char!r} "
                f"at character {index}"
            )
        output.extend(encoded)
    return bytes(output)


@dataclass(frozen=True)
class DecodedText:
    text: str
    encoding: str
    bom: bytes = b""

    def with_text(self, text: str) -> "DecodedText":
        return DecodedText(text=text, encoding=self.encoding, bom=self.bom)

    def encode(self, substitutions: Mapping[str, str] | None = None) -> bytes:
        if self.encoding == "cp932":
            return self.bom + encode_game_text(self.text, substitutions)
        text = (
            "".join(substitutions.get(char, char) for char in self.text)
            if substitutions
            else self.text
        )
        try:
            return self.bom + text.encode(self.encoding, errors="strict")
        except UnicodeEncodeError as exc:
            char = text[exc.start : exc.end]
            raise EncodingError(
                f"Cannot encode {char!r} as {self.encoding} at character {exc.start}"
            ) from exc


def decode(data: bytes) -> DecodedText:
    if data.startswith(b"\xef\xbb\xbf"):
        return DecodedText(data[3:].decode("utf-8", errors="strict"), "utf-8", b"\xef\xbb\xbf")
    if data.startswith(b"\xff\xfe"):
        return DecodedText(data[2:].decode("utf-16le", errors="strict"), "utf-16le", b"\xff\xfe")

    cp932 = _try_decode(data, "cp932")
    utf8 = _try_decode(data, "utf-8")
    if cp932 is not None and utf8 is None:
        return DecodedText(cp932, "cp932")
    if utf8 is not None and cp932 is None:
        return DecodedText(utf8, "utf-8")
    if cp932 is not None and utf8 is not None:
        return DecodedText(cp932, "cp932")
    raise EncodingError("Text is neither valid CP932 nor valid UTF-8")


def _try_decode(data: bytes, encoding: str) -> str | None:
    try:
        return data.decode(encoding, errors="strict")
    except UnicodeDecodeError:
        return None

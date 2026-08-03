from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from . import gim


SOURCE_HAN_SANS = Path.home() / "Library/Fonts/SourceHanSansSC-Normal.otf"

BF_CALL_TITLES = (
    ("角色移动", (1, -3)),
    ("跨地图移动", (1, -3)),
    ("对话开启方式", (1, -3)),
    ("可执行指令显示", (1, -3)),
    ("对话指令配色", (1, -3)),
    ("关注度", (1, -3)),
    ("关注度变化", (1, -3)),
    ("角色态度", (1, -3)),
    ("态度变化", (1, -3)),
    ("关注度数值配色", (1, -3)),
    ("关注度加成", (1, -3)),
    ("系统菜单", (1, -3)),
    ("状态", (1, -3)),
    ("选项", (1, -3)),
    ("教程", (1, -3)),
    ("返回标题画面", (1, -3)),
    ("结束日常生活", (1, -3)),
    ("情报收集", (1, -3)),
    ("情报确认", (1, -3)),
    ("地图机关调配", (1, -3)),
    ("地图机关配置", (1, -3)),
    ("配置步骤", (1, -3)),
    ("武器调配", (1, -3)),
    ("模拟战", (1, -3)),
    ("技能程序开发", (1, -3)),
    ("技能程序安装", (1, -3)),
    ("开始战斗", (1, -3)),
    ("驾驶员治疗", (1, -3)),
    ("EVA修理", (1, -3)),
    ("城市重建支援", (1, -3)),
)

BF_01_LABEL_IMAGES = (
    (0x259C, 0x2DEC, 64, 64, (
        ("时间限制：", (1, -1)),
        ("使徒出现：", (1, 15)),
        ("防卫据点：", (1, 31)),
        ("作战目标：", (1, 47)),
    )),
    (0x2E8C, 0x30DC, 64, 16, (
        ("失败条件：", (1, -1)),
    )),
)

_BF_CALL_TITLE_SIZE = 0x800
_BF_CALL_TITLE_START = 0x80
_BF_CALL_PICTURE_SIZE = 0x8D0


DECIDE_LABEL_IMAGES = (
    (0xF6D8, 32, 16, (("确认", (1, -5)),)),
    (0xF8C8, 64, 16, (("取消", (8, -5)),)),
)


def patch_decide_labels(data: bytes) -> bytes:
    patched = bytearray(data)
    font = ImageFont.truetype(SOURCE_HAN_SANS, 13)
    for target, width, height, labels in DECIDE_LABEL_IMAGES:
        encoded = _render_p4(data, None, width, height, font, labels)
        patched[target:target + len(encoded)] = encoded
    return bytes(patched)


def patch_loading_titles(data: bytes) -> bytes:
    patched = bytearray(data)
    font = ImageFont.truetype(SOURCE_HAN_SANS, 15)
    for index, (text, position) in enumerate(BF_CALL_TITLES):
        target = _BF_CALL_TITLE_START + index * _BF_CALL_PICTURE_SIZE
        palette = 0x8D0 + index * _BF_CALL_PICTURE_SIZE
        encoded = _render_p4(data, palette, 128, 32, font, ((text, position),))
        patched[target:target + _BF_CALL_TITLE_SIZE] = encoded
    return bytes(patched)


def patch_battle_briefing_labels(data: bytes) -> bytes:
    patched = bytearray(data)
    font = ImageFont.truetype(SOURCE_HAN_SANS, 12)
    for target, palette, width, height, labels in BF_01_LABEL_IMAGES:
        encoded = _render_p4(data, palette, width, height, font, labels)
        patched[target:target + len(encoded)] = encoded
    return bytes(patched)


def _render_p4(data, palette_offset, width, height, font, labels):
    mask = Image.new("L", (width, height))
    draw = ImageDraw.Draw(mask)
    for text, position in labels:
        draw.text(position, text, font=font, fill=255)

    palette_alpha = (
        tuple(range(0, 256, 17))
        if palette_offset is None
        else tuple(
            (
                (
                    int.from_bytes(
                        data[
                            palette_offset + index * 2:
                            palette_offset + index * 2 + 2
                        ],
                        "little",
                    )
                    >> 12
                )
                & 0x0F
            )
            * 17
            for index in range(16)
        )
    )
    pixels = mask.tobytes()
    rows = tuple(
        "".join(
            format(
                0 if alpha == 0 else min(
                    range(16),
                    key=lambda index: (abs(palette_alpha[index] - alpha), -index),
                ),
                "x",
            )
            for alpha in pixels[y * width:(y + 1) * width]
        )
        for y in range(height)
    )
    return gim.encode_p4_swizzled(rows)

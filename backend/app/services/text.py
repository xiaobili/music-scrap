from __future__ import annotations

from collections.abc import Callable

import zhconv


def has_cjk(text: str | None) -> bool:
    return bool(text) and any("\u4e00" <= char <= "\u9fff" for char in text)


def to_simplified(text: str) -> str:
    return zhconv.convert(text, "zh-hans")


def to_traditional(text: str) -> str:
    return zhconv.convert(text, "zh-hant")


def _convert(convert: Callable[[str], str], text: str | None) -> str | None:
    return convert(text) if text else text


def field_variants(
    album: str | None, artist: str | None
) -> list[tuple[str | None, str | None]]:
    """返回原始、全简体、全繁体三种字段组合，供跨简繁检索使用。

    纯非中文输入不产生额外变体，避免成倍增加外部请求。
    """
    if not has_cjk(album) and not has_cjk(artist):
        return [(album, artist)]
    variants: list[tuple[str | None, str | None]] = [(album, artist)]
    for convert in (to_simplified, to_traditional):
        pair = (_convert(convert, album), _convert(convert, artist))
        if pair not in variants:
            variants.append(pair)
    return variants

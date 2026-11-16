from __future__ import annotations

from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image

MAX_COVER_BYTES = 10 * 1024 * 1024
MIN_COVER_SIDE = 500
MAX_COVER_SIDE = 1500


class CoverError(Exception):
    pass


async def download_cover(
    client: httpx.AsyncClient, url: str, *, max_bytes: int = MAX_COVER_BYTES
) -> bytes:
    response = await client.get(url, follow_redirects=True)
    if response.status_code != 200:
        raise CoverError(f"cover download failed: HTTP {response.status_code}")
    if len(response.content) > max_bytes:
        raise CoverError("cover is larger than 10MB")
    return response.content


def process_cover(data: bytes) -> bytes:
    if len(data) > MAX_COVER_BYTES:
        raise CoverError("cover is larger than 10MB")
    try:
        image = Image.open(BytesIO(data))
        image.load()
    except Exception as exc:
        raise CoverError("invalid image data") from exc
    if max(image.size) < MIN_COVER_SIDE:
        raise CoverError(f"cover is smaller than {MIN_COVER_SIDE}px")
    image = image.convert("RGB")
    if max(image.size) > MAX_COVER_SIDE:
        image.thumbnail((MAX_COVER_SIDE, MAX_COVER_SIDE))
    output = BytesIO()
    image.save(output, format="JPEG", quality=90, optimize=True)
    return output.getvalue()


def save_cover_jpg(directory: Path, data: bytes, policy: str) -> Path | None:
    target = directory / "cover.jpg"
    if policy == "never":
        return None
    if policy == "if_missing" and target.exists():
        return None
    target.write_bytes(data)
    return target

"""Распознавание штрихкода на фото (EAN/UPC) через zxing-cpp."""

from __future__ import annotations

import asyncio
import io
import logging

from PIL import Image, ImageOps, UnidentifiedImageError

log = logging.getLogger(__name__)

MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 40_000_000
MAX_SIDE = 2000
PRODUCT_FORMATS = ("EAN13", "EAN8", "UPCA", "UPCE")


class BarcodeError(ValueError):
    """Фото не удалось прочитать."""


def _prepare(data: bytes) -> Image.Image:
    if len(data) > MAX_IMAGE_BYTES:
        raise BarcodeError("Фото слишком большое (больше 8 МБ)")
    try:
        image = Image.open(io.BytesIO(data))
        width, height = image.size
        if width * height > MAX_PIXELS:
            raise BarcodeError("Фото слишком большое по размеру — уменьшите его")
        image.draft("L", (MAX_SIDE, MAX_SIDE))  # JPEG сразу читается уменьшенным
        image = ImageOps.exif_transpose(image).convert("L")
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
        raise BarcodeError("Не получилось открыть фото") from exc
    image.thumbnail((MAX_SIDE, MAX_SIDE))
    return image


async def decode_async(data: bytes) -> str | None:
    """Распознавание тяжёлое — уводим из цикла событий, чтобы не тормозить бота и API."""
    return await asyncio.to_thread(decode, data)


def decode(data: bytes) -> str | None:
    import zxingcpp  # тяжёлый модуль — грузим по требованию

    image = _prepare(data)
    for candidate in (image, ImageOps.autocontrast(image)):
        results = zxingcpp.read_barcodes(candidate)
        for result in results:
            fmt = str(result.format).split(".")[-1].upper().replace("_", "").replace("-", "")
            if any(fmt.startswith(p) for p in PRODUCT_FORMATS) and result.text.isdigit():
                return result.text
        for result in results:
            if result.text.isdigit():
                return result.text
    log.info("barcode not found in image %sx%s", *image.size)
    return None

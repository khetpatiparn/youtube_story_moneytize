from __future__ import annotations

import io
from dataclasses import dataclass
from pathlib import Path
from xml.etree import ElementTree

from PIL import Image, UnidentifiedImageError


MAX_IMAGE_BYTES = 16 * 1024 * 1024


@dataclass(frozen=True)
class ImageMetadata:
    mime_type: str
    width: int
    height: int
    format: str


def validate_image_bytes(content: bytes, mime_type: str) -> ImageMetadata:
    if mime_type == "image/svg+xml":
        return _validate_svg(content)
    if mime_type == "image/jpeg":
        return _validate_jpeg(content)
    raise ValueError("unsupported image MIME type")


def validate_image_file(path: Path, mime_type: str) -> ImageMetadata:
    try:
        with path.open("rb") as image_file:
            content = image_file.read(MAX_IMAGE_BYTES + 1)
    except OSError as error:
        raise ValueError("image file could not be read") from error
    if len(content) > MAX_IMAGE_BYTES:
        raise ValueError("image file exceeds 16 MB")
    return validate_image_bytes(content, mime_type)


def _validate_svg(content: bytes) -> ImageMetadata:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as error:
        raise ValueError("output SVG is not parseable") from error
    if root.tag != "{http://www.w3.org/2000/svg}svg":
        raise ValueError("output XML root must be the SVG namespace element")
    expected_canvas = {
        "width": "1280",
        "height": "720",
        "viewBox": "0 0 1280 720",
    }
    for attribute, expected in expected_canvas.items():
        if root.get(attribute) != expected:
            raise ValueError(f"output SVG {attribute} must be {expected!r}")
    return ImageMetadata("image/svg+xml", 1280, 720, "SVG")


def _validate_jpeg(content: bytes) -> ImageMetadata:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image.load()
            image_format = image.format
            width, height = image.size
    except (OSError, SyntaxError, ValueError, UnidentifiedImageError, Image.DecompressionBombError) as error:
        raise ValueError("output JPEG is invalid") from error
    if image_format != "JPEG":
        raise ValueError("output image format must be JPEG")
    if not 512 <= width <= 4096 or not 512 <= height <= 4096:
        raise ValueError("output JPEG dimensions must each be between 512 and 4096 pixels")
    return ImageMetadata("image/jpeg", width, height, image_format)

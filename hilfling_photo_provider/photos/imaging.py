import io
from pathlib import Path

import exifread
from PIL import ExifTags, Image, ImageOps


def save_web(image_data: bytes, dest: Path, max_size: int = 1000, quality: int = 100) -> None:
    """Resize to fit within max_size x max_size, preserving aspect ratio."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        img.save(dest, quality=quality, optimize=True)


def save_thumb(image_data: bytes, dest: Path, size: int = 300, quality: int = 50) -> None:
    """Center-crop to square then resize to size x size."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        w, h = img.size
        crop_side = min(w, h)
        left = (w - crop_side) // 2
        top = (h - crop_side) // 2
        img = img.crop((left, top, left + crop_side, top + crop_side))
        img = img.resize((size, size), Image.LANCZOS)
        img.save(dest, quality=quality, optimize=True)


def _exif_text(tags, key):
    tag = tags.get(key)
    return str(tag) if tag else None


def _exif_number(tags, key):
    tag = tags.get(key)
    return float(tag.values[0]) if tag and tag.values else None


def read_metadata(path: Path) -> dict:
    """EXIF and size info for an image file. Raises if the file cannot be read as an image."""
    with path.open("rb") as f:
        tags = exifread.process_file(f, details=False)
    with Image.open(path) as img:
        width, height = img.size
        orientation = img.getexif().get(ExifTags.Base.Orientation, 1)

    # Orientation 5-8 means the image is stored rotated 90°
    if orientation in (5, 6, 7, 8):
        width, height = height, width

    iso = _exif_number(tags, "EXIF ISOSpeedRatings")

    return {
        "model": _exif_text(tags, "Image Model"),
        "lensModel": _exif_text(tags, "EXIF LensModel"),
        "iso": int(iso) if iso is not None else None,
        "fNumber": _exif_number(tags, "EXIF FNumber"),
        "exposureTime": _exif_number(tags, "EXIF ExposureTime"),
        "focalLength": _exif_number(tags, "EXIF FocalLength"),
        "exposureCompensation": _exif_number(tags, "EXIF ExposureBiasValue"),
        "flash": _exif_text(tags, "EXIF Flash"),
        "imageWidth": width,
        "imageHeight": height,
        "fileSize": path.stat().st_size,
    }

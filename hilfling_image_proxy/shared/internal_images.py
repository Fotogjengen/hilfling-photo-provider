"""File storage for images owned by the backend, independent of archive albums."""

import io
import logging
import os
import tempfile
import warnings
from pathlib import Path

from django.conf import settings
from django.http import HttpResponse, JsonResponse
from PIL import Image, ImageOps, UnidentifiedImageError

from hilfling_image_proxy.utils.auth import InvalidToken, verify_storage_token

logger = logging.getLogger(__name__)
VARIANTS = ("prod.png", "prod.jpg", "prod.webp", "web.png", "thumb.png")
FORMATS = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png"), "WEBP": ("webp", "image/webp")}


def _directory(image_id, security_level):
    root = Path(settings.IMAGE_STORAGE_PATH).resolve()
    destination = root / security_level.lower() / "internal" / str(image_id)
    # Never follow a symlink out of storage, including in an existing parent.
    if not destination.resolve().is_relative_to(root):
        raise ValueError("Invalid storage path")
    return destination


def _remove_variants(directory):
    for name in VARIANTS:
        (directory / name).unlink(missing_ok=True)


def internal_image_view(request, image_id):
    if request.method not in ("POST", "DELETE"):
        response = JsonResponse({"error": "Method not allowed"}, status=405)
        response["Allow"] = "POST, DELETE"
        return response

    try:
        claims = verify_storage_token(request, image_id, request.method)
    except InvalidToken:
        return JsonResponse({"error": "Invalid storage token"}, status=401)

    try:
        directory = _directory(image_id, claims["securityLevel"])
        if request.method == "DELETE":
            directory.mkdir(parents=True, exist_ok=True)
            # A tombstone also cancels uploads still running after a backend timeout.
            (directory / ".deleted").touch()
            _remove_variants(directory)
            return HttpResponse(status=204)
        return _upload(request, directory, image_id, claims["securityLevel"])
    except (OSError, ValueError):
        logger.exception("Image storage operation failed for %s", image_id)
        return JsonResponse({"error": "Image storage unavailable"}, status=503)


def _upload(request, directory, image_id, security_level):
    media = request.FILES.get("media")
    if media is None:
        return JsonResponse({"error": "media is required"}, status=400)
    if media.size > settings.INTERNAL_IMAGE_MAX_BYTES:
        return JsonResponse({"error": "Image exceeds the upload limit"}, status=413)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image_data = media.read(settings.INTERNAL_IMAGE_MAX_BYTES + 1)
            if len(image_data) > settings.INTERNAL_IMAGE_MAX_BYTES:
                return JsonResponse({"error": "Image exceeds the upload limit"}, status=413)
            with Image.open(io.BytesIO(image_data)) as source:
                image_format = source.format
                if image_format not in FORMATS:
                    return JsonResponse({"error": "Use JPEG, PNG or WebP"}, status=400)
                if source.width * source.height > settings.INTERNAL_IMAGE_MAX_PIXELS:
                    return JsonResponse({"error": "Image dimensions are too large"}, status=400)
                source.load()  # Decode fully: truncated/corrupt files must not be published.
                oriented = ImageOps.exif_transpose(source)
                # Normalize raster data; no EXIF/GPS metadata is copied to public profiles.
                mode = "RGBA" if "A" in oriented.getbands() or "transparency" in oriented.info else "RGB"
                img = oriented.convert(mode)
                img.info.clear()
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        return JsonResponse({"error": "Invalid image"}, status=400)

    extension, content_type = FORMATS[image_format]
    if directory.exists():
        return JsonResponse({"error": "Image already exists or was deleted"}, status=409)

    # Finish every variant outside the served directory before publishing any of them.
    staging_root = Path(settings.IMAGE_STORAGE_PATH).resolve() / ".uploads"
    staging_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=staging_root) as staging:
        staging = Path(staging)
        prod_name = f"prod.{extension}"
        img.save(staging / prod_name, format=image_format, **({"quality": 95} if image_format in {"JPEG", "WEBP"} else {}))
        web = img.copy()
        web.thumbnail((1000, 1000), Image.Resampling.LANCZOS)
        web.save(staging / "web.png", format="PNG")
        thumb = ImageOps.fit(img, (300, 300), method=Image.Resampling.LANCZOS)
        thumb.save(staging / "thumb.png", format="PNG")
        size = (staging / prod_name).stat().st_size

        try:
            directory.mkdir(parents=True, exist_ok=False)
        except FileExistsError:
            return JsonResponse({"error": "Image already exists or was deleted"}, status=409)
        try:
            for name in (prod_name, "web.png", "thumb.png"):
                os.replace(staging / name, directory / name)
            if (directory / ".deleted").exists():
                _remove_variants(directory)
                return JsonResponse({"error": "Upload was cancelled"}, status=409)
        except OSError:
            (directory / ".deleted").touch()
            _remove_variants(directory)
            raise

    base = f"{settings.IMAGE_BASE_URL.rstrip('/')}/{security_level.lower()}/internal/{image_id}"
    return JsonResponse({
        "prod": f"{base}/{prod_name}",
        "web": f"{base}/web.png",
        "thumb": f"{base}/thumb.png",
        "contentType": content_type,
        "fileSize": size,
        "width": img.width,
        "height": img.height,
    }, status=201)

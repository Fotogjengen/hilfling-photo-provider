import io
import re
import unicodedata
import uuid
from pathlib import Path

import requests
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from PIL import Image

from .forms import PhotoUploadForm


def _slugify(name: str) -> str:
    """Convert a string to a filesystem/URL-safe slug (ASCII, no spaces)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_name).strip("_")


def _build_filename(album: str, ext: str) -> str:
    return f"{_slugify(album).lower()}_{uuid.uuid4().hex}.{ext}"


def _relative_path(security_level: str, quality: str, album: str, filename: str) -> str:
    return f"{security_level.lower()}/{quality}/{_slugify(album).upper()}/{filename}"


def _save_web(image_data: bytes, dest: Path, max_size: int = 1000, quality: int = 100) -> None:
    """Resize to fit within max_size x max_size, preserving aspect ratio."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        img.save(dest, quality=quality, optimize=True)


def _save_thumb(image_data: bytes, dest: Path, size: int = 300, quality: int = 50) -> None:
    """Center-crop to square then resize to size x size."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = img.convert("RGB")
        w, h = img.size
        crop_side = min(w, h)
        left = (w - crop_side) // 2
        top = (h - crop_side) // 2
        img = img.crop((left, top, left + crop_side, top + crop_side))
        img = img.resize((size, size), Image.LANCZOS)
        img.save(dest, quality=quality, optimize=True)


def photo_upload_view(request: HttpRequest):
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    form = PhotoUploadForm(request.POST, request.FILES)
    if not form.is_valid():
        return JsonResponse(
            {"error": "Invalid parameters", "field_errors": form.errors},
            status=400,
        )

    data = form.cleaned_data
    backend_url = settings.PROXY_TARGET_URL
    auth_headers = {}
    token = request.META.get("HTTP_X_HILFLING_TOKEN")
    if token:
        auth_headers["X-hilfling-token"] = token

    # Step 2: Pre-validate metadata with backend before touching the filesystem.
    validate_resp = requests.post(
        f"{backend_url}/photos/upload/validate",
        data={
            "motiveId": data["motive"],
            "placeId": data["place"],
            "photoGangBangerId": str(data["photographer_id"]),
            "albumId": data["album"],
            "categoryId": data["category"],
            "eventOwnerId": data["event_owner"],
        },
        headers=auth_headers,
        timeout=10,
    )

    if validate_resp.status_code != 200:
        return JsonResponse({"error": "Backend validation request failed"}, status=502)

    validate_data = validate_resp.json()
    if not validate_data.get("valid"):
        return JsonResponse(
            {"error": "Upload parameters invalid", "errors": validate_data.get("errors", [])},
            status=400,
        )

    # Step 3: Save the image in three sizes under the correct directory structure:
    #   <security_level_lower>/<quality>/<ALBUM_UPPER>/<filename>
    image_file = data["media"]
    album = data["album"]
    security_level = data["security_level"]
    ext = image_file.name.rsplit(".", 1)[-1].lower() if "." in image_file.name else "jpg"

    filename = _build_filename(album, ext)
    storage_root = Path(settings.IMAGE_STORAGE_PATH)

    prod_rel = _relative_path(security_level, "prod", album, filename)
    web_rel = _relative_path(security_level, "web", album, filename)
    thumb_rel = _relative_path(security_level, "thumb", album, filename)

    prod_abs = storage_root / prod_rel
    web_abs = storage_root / web_rel
    thumb_abs = storage_root / thumb_rel

    image_data = image_file.read()

    for path in (prod_abs, web_abs, thumb_abs):
        path.parent.mkdir(parents=True, exist_ok=True)

    prod_abs.write_bytes(image_data)
    _save_web(image_data, web_abs)
    _save_thumb(image_data, thumb_abs)

    image_base_url = settings.IMAGE_BASE_URL.rstrip("/")
    prod_url = f"{image_base_url}/{prod_rel}"
    web_url = f"{image_base_url}/{web_rel}"
    thumb_url = f"{image_base_url}/{thumb_rel}"

    # Step 4: Commit the DB entry to the backend.
    commit_data = {
        "motiveTitle": data["motive"],
        "placeName": data["place"],
        "securityLevel": security_level,
        "photoGangBangerId": str(data["photographer_id"]),
        "albumTitle": album,
        "categoryName": data["category"],
        "eventOwnerName": data["event_owner"],
        "largeUrl": prod_url,
        "mediumUrl": web_url,
        "smallUrl": thumb_url,
        "isGoodPhoto": str(data.get("is_good_picture", False)).lower(),
        "dateTaken": data["date"].isoformat(),
    }
    tags = request.POST.getlist("tag")
    if tags:
        commit_data["tagList"] = tags
    commit_resp = requests.post(
        f"{backend_url}/photos/upload",
        headers=auth_headers,
        data=commit_data,
        timeout=10,
    )

    if commit_resp.status_code not in (200, 201):
        for path in (prod_abs, web_abs, thumb_abs):
            path.unlink(missing_ok=True)
        return JsonResponse({"error": "Failed to save photo metadata"}, status=500)

    return JsonResponse(
        {"ok": True, "prod": prod_url, "web": web_url, "thumb": thumb_url},
        status=201,
    )

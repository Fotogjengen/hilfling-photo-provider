import io
import re
import unicodedata
from pathlib import Path

import requests
from django.conf import settings
from django.http import HttpRequest, JsonResponse
from PIL import Image, ImageOps

from .forms import PhotoUploadForm


def _slugify(name: str) -> str:
    """Convert a string to a filesystem/URL-safe slug (ASCII, no spaces)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_name).strip("_")



def _build_filename(album: str, page_number: int, image_number: int, ext: str) -> str:
    return f"{_slugify(album).lower()}{page_number}{image_number}.{ext}"


def _relative_path(security_level: str, quality: str, album: str, filename: str) -> str:
    return f"{security_level.lower()}/{quality}/{_slugify(album).upper()}/{filename}"


def _save_web(image_data: bytes, dest: Path, max_size: int = 1000, quality: int = 100) -> None:
    """Resize to fit within max_size x max_size, preserving aspect ratio."""
    with Image.open(io.BytesIO(image_data)) as img:
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        img.thumbnail((max_size, max_size), Image.LANCZOS)
        img.save(dest, quality=quality, optimize=True)


def _save_thumb(image_data: bytes, dest: Path, size: int = 300, quality: int = 50) -> None:
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

    # Step 2: Reserve a slot in the backend before touching the filesystem.
    reserve_payload = {
        "motiveId": str(data["motive_id"]),
        "dateTaken": data["date"].isoformat(),
        "goodPicture": bool(data.get("good_picture", False)),
        "analog": bool(data.get("analog", False)),
    }
    if data.get("gang_id"):
        reserve_payload["gangId"] = str(data["gang_id"])

    reserve_resp = requests.post(
        f"{backend_url}/photos/upload/reserve",
        json=reserve_payload,
        headers=auth_headers,
        timeout=10,
    )

    if reserve_resp.status_code != 200:
        try:
            body = reserve_resp.json()
        except Exception:
            body = {"error": reserve_resp.text}
        return JsonResponse(body, status=reserve_resp.status_code, safe=False)

    reservation = reserve_resp.json()

    # Step 3: Save the image in three sizes under the correct directory structure:
    #   <security_level_lower>/<quality>/<ALBUM_UPPER>/<filename>
    image_file = data["media"]
    album = reservation["album"]["name"]
    security_level = data["security_level"]
    ext = image_file.name.rsplit(".", 1)[-1].lower() if "." in image_file.name else "jpg"

    filename = _build_filename(album, reservation["pageNumber"], reservation["imageNumber"], ext)
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

    # Step 4: Finalize the DB entry in the backend.
    finalize_payload = {
        "goodPicture": bool(data.get("good_picture", False)),
        "analog": bool(data.get("analog", False)),
        "pageNumber": reservation["pageNumber"],
        "imageNumber": reservation["imageNumber"],
        "imageProd": prod_url,
        "imageWeb": web_url,
        "imageThumb": thumb_url,
        "motiveId": str(data["motive_id"]),
        "dateTaken": data["date"].isoformat(),
    }
    if data.get("gang_id"):
        finalize_payload["gangId"] = str(data["gang_id"])

    finalize_resp = requests.post(
        f"{backend_url}/photos/upload/finalize",
        json=finalize_payload,
        headers=auth_headers,
        timeout=10,
    )

    if finalize_resp.status_code not in (200, 201):
        for path in (prod_abs, web_abs, thumb_abs):
            path.unlink(missing_ok=True)
        try:
            body = finalize_resp.json()
        except Exception:
            body = {"error": finalize_resp.text}
        return JsonResponse(body, status=finalize_resp.status_code, safe=False)

    return JsonResponse(
        {"ok": True, "prod": prod_url, "web": web_url, "thumb": thumb_url},
        status=201,
    )


def photo_delete_view(request: HttpRequest, photo_id: str):
    backend_url = settings.PROXY_TARGET_URL
    auth_headers = {}
    token = request.META.get("HTTP_X_HILFLING_TOKEN")
    if token:
        auth_headers["X-hilfling-token"] = token

    if request.method != "DELETE":
        resp = requests.request(
            method=request.method,
            url=f"{backend_url}/photos/{photo_id}",
            headers=auth_headers,
            params=request.GET,
            timeout=10,
        )
        try:
            return JsonResponse(resp.json(), status=resp.status_code, safe=False)
        except Exception:
            return JsonResponse({"error": resp.text}, status=resp.status_code)

    backend_resp = requests.delete(
        f"{backend_url}/photos/{photo_id}",
        headers=auth_headers,
        params=request.GET,
        timeout=10,
    )

    if backend_resp.status_code not in (200, 204):
        try:
            body = backend_resp.json()
        except Exception:
            body = {"error": backend_resp.text}
        return JsonResponse(body, status=backend_resp.status_code, safe=False)

    photo = backend_resp.json()

    image_base_url = settings.IMAGE_BASE_URL.rstrip("/")
    storage_root = Path(settings.IMAGE_STORAGE_PATH)

    for url_field in ("imageProd", "imageWeb", "imageThumb"):
        url = photo.get(url_field, "")
        if url.startswith(image_base_url):
            rel = url[len(image_base_url):].lstrip("/")
            (storage_root / rel).unlink(missing_ok=True)

    return JsonResponse(photo, status=backend_resp.status_code, safe=False)

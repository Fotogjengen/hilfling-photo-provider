import io
import json
import os
import re
import unicodedata
from pathlib import Path

import exifread
import requests
from django.conf import settings
from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, HttpRequest, JsonResponse
from django.utils._os import safe_join
from PIL import ExifTags, Image, ImageOps

from hilfling_image_proxy.utils.auth import InvalidToken, can_access

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
    # Forward the JWT from the cookie to the backend as a header
    token = request.COOKIES.get("fgToken")
    if token:
        auth_headers["X-hilfling-token"] = token

    # Reserve an image slot in the backend before writing to disk
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

    # save the image in three sizes under the correct directory structure:
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

    # Finalize the DB entry in the backend.
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

    # Forward the JWT from the cookie to the backend as a header
    token = request.COOKIES.get("fgToken")
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


def serve_image_view(request: HttpRequest, path: str):
    """Serve a stored image, gated by the requester's token security level.

    Images live under <storage>/<security_level>/<quality>/<ALBUM>/<file>, so the
    first path segment is the security level. Public images (ALLE) are served to
    anyone; FG/HUSFOLK images require a token whose securityLevel permits them.
    """
    if request.method not in ("GET", "HEAD"):
        return JsonResponse({"error": "Method not allowed"}, status=405)

    storage_root = settings.IMAGE_STORAGE_PATH
    try:
        abs_path = Path(safe_join(storage_root, path))
    except (ValueError, SuspiciousFileOperation):
        return JsonResponse({"error": "Not found"}, status=404)

    required_level = path.strip("/").split("/", 1)[0].upper()
    try:
        allowed = can_access(request, required_level)
    except InvalidToken:
        return JsonResponse({"error": "Invalid token"}, status=401)
    if not allowed:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if not abs_path.is_file():
        return JsonResponse({"error": "Not found"}, status=404)

    return FileResponse(abs_path.open("rb"))


def _exif_text(tags, key):
    tag = tags.get(key)
    return str(tag) if tag else None


def _exif_number(tags, key):
    tag = tags.get(key)
    return float(tag.values[0]) if tag and tag.values else None


def photo_metadata_view(request: HttpRequest, path: str):
    """Return EXIF metadata for a stored image, gated like serve_image_view."""
    if request.method != "GET":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    storage_root = settings.IMAGE_STORAGE_PATH
    try:
        abs_path = Path(safe_join(storage_root, path))
    except (ValueError, SuspiciousFileOperation):
        return JsonResponse({"error": "Not found"}, status=404)

    required_level = path.strip("/").split("/", 1)[0].upper()
    try:
        allowed = can_access(request, required_level)
    except InvalidToken:
        return JsonResponse({"error": "Invalid token"}, status=401)
    if not allowed:
        return JsonResponse({"error": "Forbidden"}, status=403)

    if not abs_path.is_file():
        return JsonResponse({"error": "Not found"}, status=404)

    try:
        with abs_path.open("rb") as f:
            tags = exifread.process_file(f, details=False)
        with Image.open(abs_path) as img:
            width, height = img.size
            orientation = img.getexif().get(ExifTags.Base.Orientation, 1)
    except Exception:
        return JsonResponse({"error": "Not an image"}, status=422)

    # Orientation 5-8 means the image is stored rotated 90°
    if orientation in (5, 6, 7, 8):
        width, height = height, width

    iso = _exif_number(tags, "EXIF ISOSpeedRatings")

    metadata = {
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
        "fileSize": abs_path.stat().st_size,
    }

    response = JsonResponse(metadata)
    response["Cache-Control"] = "private, max-age=86400"
    return response


def _forward_backend_json(resp):
    """Re-serialize a backend requests.Response as a Django JsonResponse."""
    try:
        body = resp.json()
    except Exception:
        return JsonResponse({"error": resp.text}, status=resp.status_code)
    return JsonResponse(body, status=resp.status_code, safe=False)


def photo_move_view(request: HttpRequest, photo_id: str):
    """Move a photo to a different motive (and, when needed, a different album).

    Orchestrates a two-phase backend flow mirroring the upload path:
      1. POST /photos/{id}/move/reserve  -> learns whether files must move and,
         if so, the destination album/slot/security level plus the current URLs.
      2. When files must move, rename the prod/web/thumb files on disk from the
         old paths (derived from the current URLs) to the new paths (derived
         from the target album/slot/security level).
      3. POST /photos/{id}/move/finalize -> commits the motive/slot/URL/security
         level change in the DB. On failure the file renames are rolled back.
    """
    if request.method != "POST":
        return JsonResponse({"error": "Method not allowed"}, status=405)

    try:
        body = json.loads(request.body or b"{}")
    except (ValueError, json.JSONDecodeError):
        return JsonResponse({"error": "Invalid JSON body"}, status=400)
    target_motive_id = body.get("targetMotiveId")
    if not target_motive_id:
        return JsonResponse({"error": "targetMotiveId is required"}, status=400)

    backend_url = settings.PROXY_TARGET_URL
    auth_headers = {}
    token = request.COOKIES.get("fgToken")
    if token:
        auth_headers["X-hilfling-token"] = token

    reserve_resp = requests.post(
        f"{backend_url}/photos/{photo_id}/move/reserve",
        json={"targetMotiveId": target_motive_id},
        headers=auth_headers,
        timeout=10,
    )
    if reserve_resp.status_code != 200:
        return _forward_backend_json(reserve_resp)

    reservation = reserve_resp.json()
    page_number = reservation["pageNumber"]
    image_number = reservation["imageNumber"]
    current_prod = reservation.get("currentImageProd")
    current_web = reservation.get("currentImageWeb")
    current_thumb = reservation.get("currentImageThumb")

    # No file relocation needed: same album and same security level. Just
    # finalise with the unchanged slot and URLs.
    if not reservation.get("fileMoveRequired"):
        finalize_payload = {
            "targetMotiveId": target_motive_id,
            "pageNumber": page_number,
            "imageNumber": image_number,
            "imageProd": current_prod,
            "imageWeb": current_web,
            "imageThumb": current_thumb,
        }
        finalize_resp = requests.post(
            f"{backend_url}/photos/{photo_id}/move/finalize",
            json=finalize_payload,
            headers=auth_headers,
            timeout=10,
        )
        return _forward_backend_json(finalize_resp)

    album = reservation["albumName"]
    security_level = reservation["securityLevel"]
    storage_root = Path(settings.IMAGE_STORAGE_PATH)
    image_base_url = settings.IMAGE_BASE_URL.rstrip("/")

    old_urls = {"prod": current_prod, "web": current_web, "thumb": current_thumb}

    ext = "jpg"
    for u in (current_thumb, current_prod):
        fname = (u or "").rsplit("/", 1)[-1]
        if "." in fname:
            ext = fname.rsplit(".", 1)[-1].lower()
            break

    filename = _build_filename(album, page_number, image_number, ext)

    moved = []  # list of (new_abs, old_abs) for rollback
    try:
        for quality, url in old_urls.items():
            if not url or not url.startswith(image_base_url):
                continue
            old_rel = url[len(image_base_url):].lstrip("/")
            old_abs = storage_root / old_rel
            if not old_abs.is_file():
                continue
            new_rel = _relative_path(security_level, quality, album, filename)
            new_abs = storage_root / new_rel
            new_abs.parent.mkdir(parents=True, exist_ok=True)
            os.replace(old_abs, new_abs)
            moved.append((new_abs, old_abs))
    except OSError as exc:
        for new_abs, old_abs in moved:
            try:
                os.replace(new_abs, old_abs)
            except OSError:
                pass
        return JsonResponse({"error": f"Failed to move image files: {exc}"}, status=500)

    finalize_payload = {
        "targetMotiveId": target_motive_id,
        "pageNumber": page_number,
        "imageNumber": image_number,
        "imageProd": f"{image_base_url}/{_relative_path(security_level, 'prod', album, filename)}",
        "imageWeb": f"{image_base_url}/{_relative_path(security_level, 'web', album, filename)}",
        "imageThumb": f"{image_base_url}/{_relative_path(security_level, 'thumb', album, filename)}",
    }
    finalize_resp = requests.post(
        f"{backend_url}/photos/{photo_id}/move/finalize",
        json=finalize_payload,
        headers=auth_headers,
        timeout=10,
    )
    if finalize_resp.status_code not in (200, 201):
        # Roll back the file moves so disk and DB stay consistent.
        for new_abs, old_abs in moved:
            try:
                os.replace(new_abs, old_abs)
            except OSError:
                pass
    return _forward_backend_json(finalize_resp)

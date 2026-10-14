"""Provider-internal endpoints, called only by the backend with a service token (see verify_service_request).

The backend decides where photos belong (security level, album, slot); the paths are built here.
"""

import json
import logging
from pathlib import Path

from django.core.exceptions import SuspiciousFileOperation
from django.http import JsonResponse

from hilfling_photo_provider.utils.security_level import SecurityLevel

from ..http import ApiError, api_view, service_scope
from ..storage import (
    QUALITIES,
    RelocationConflict,
    build_filename,
    image_url,
    move_file,
    relative_path,
    storage_path,
    stored_rel,
    undo_moves,
    valid_stored_path,
)

logger = logging.getLogger(__name__)

_BAD_REQUEST = (KeyError, TypeError, ValueError, AttributeError, SuspiciousFileOperation)


def _parse_photos(request) -> list[dict]:
    return json.loads(request.body)["photos"]


def _image_ext(current: dict) -> str:
    for url in (current.get("thumb"), current.get("prod")):
        fname = (url or "").rsplit("/", 1)[-1]
        if "." in fname:
            return fname.rsplit(".", 1)[-1].lower()
    return "jpg"


def _relocate_photo(photo: dict, moved: list[tuple[Path, Path]]) -> dict:
    security_level = str(photo["securityLevel"])
    if security_level.upper() not in SecurityLevel.values:
        raise ValueError(f"Unknown security level {security_level}")
    album = str(photo["album"])
    current = photo["current"]
    filename = build_filename(album, int(photo["pageNumber"]), int(photo["imageNumber"]), _image_ext(current))

    new_urls = {}
    for quality in QUALITIES:
        url = current.get(quality)
        src_rel = stored_rel(url)
        if src_rel is None:
            new_urls[quality] = url
            continue
        dst_rel = relative_path(security_level, quality, album, filename)
        if not valid_stored_path(dst_rel):
            raise ValueError(f"Invalid target path {dst_rel}")
        if dst_rel != src_rel:
            result = move_file(src_rel, dst_rel)
            if result:
                moved.append(result)
        new_urls[quality] = image_url(dst_rel)

    return {
        "photoId": photo["photoId"],
        "imageProd": new_urls["prod"],
        "imageWeb": new_urls["web"],
        "imageThumb": new_urls["thumb"],
    }


def _relocate_all(photos: list[dict]) -> list[dict]:
    moved: list[tuple[Path, Path]] = []
    try:
        return [_relocate_photo(photo, moved) for photo in photos]
    except Exception:
        undo_moves(moved)
        raise


@api_view("POST")
@service_scope("relocate")
def photo_relocate_view(request):
    """Move photos' files to the location given by their security level, album and slot.

    Body: {"photos": [{"photoId", "current": {"prod", "web", "thumb"}, "securityLevel", "album", "pageNumber",
    "imageNumber"}]}. Responds with the new URLs per photo. All-or-nothing: on any failure every move is undone.
    Safe to repeat: files already at their target count as moved.
    """
    try:
        results = _relocate_all(_parse_photos(request))
    except RelocationConflict as exc:
        logger.warning("relocate conflict: %s", exc)
        raise ApiError(str(exc), 409) from exc
    except _BAD_REQUEST as exc:
        raise ApiError(f"Invalid relocate request: {exc}", 400) from exc
    except OSError as exc:
        logger.exception("relocate failed")
        raise ApiError(f"Failed to move image files: {exc}", 500) from exc

    return JsonResponse({"photos": results})


@api_view("POST")
@service_scope("delete")
def photo_delete_view(request):
    """Unlink photos' files. Body: {"photos": [{"photoId", "current": {"prod", "web", "thumb"}}]}.

    Files already gone count as deleted; URLs we don't serve are ignored.
    """
    try:
        rels = [
            rel
            for photo in _parse_photos(request)
            for quality in QUALITIES
            if (rel := stored_rel(photo["current"].get(quality)))
        ]
        for rel in rels:
            storage_path(rel).unlink(missing_ok=True)
    except _BAD_REQUEST as exc:
        raise ApiError(f"Invalid delete request: {exc}", 400) from exc

    return JsonResponse({"deleted": len(rels)})

from pathlib import Path

from django.core.exceptions import SuspiciousFileOperation
from django.http import FileResponse, JsonResponse

from ..http import ApiError, api_view, require_access
from ..imaging import read_metadata
from ..storage import StoredPath, storage_path


def _authorized_file(request, path: str, *, members_only_prod: bool) -> Path:
    """Resolve a request path to an existing file the requester may view, else raise ApiError."""
    try:
        abs_path = storage_path(path)
    except (ValueError, SuspiciousFileOperation):
        raise ApiError("Not found", 404)

    stored = StoredPath.parse(path)
    require_access(request, stored.level, prod=members_only_prod and stored.is_prod)

    if not abs_path.is_file():
        raise ApiError("Not found", 404)
    return abs_path


@api_view("GET", "HEAD")
def serve_image_view(request, path: str):
    """Serve a stored image, gated by the requester's token security level.

    The security level is derived from the path (see StoredPath). Public images
    (ALLE) are served to anyone; FG/HUSFOLK images require a token whose
    securityLevel permits them. Full-resolution prod files are members-only on
    top of that: they always require an FG or HUSFOLK token, even for photos
    whose security level is ALLE. Metadata is exempt from the prod gate and only
    follows the photo's security level (see photo_metadata_view).
    """
    abs_path = _authorized_file(request, path, members_only_prod=True)
    return FileResponse(abs_path.open("rb"))


@api_view("GET")
def photo_metadata_view(request, path: str):
    """Return EXIF metadata for a stored image.

    Gated by the image's security level only: unlike serve_image_view, the
    members-only gate on prod files does not apply, so anyone who may view a
    photo (including unauthenticated users for ALLE photos) can always read
    the metadata of its prod image.
    """
    abs_path = _authorized_file(request, path, members_only_prod=False)
    try:
        metadata = read_metadata(abs_path)
    except Exception:
        raise ApiError("Not an image", 422)

    response = JsonResponse(metadata)
    response["Cache-Control"] = "private, max-age=86400"
    return response

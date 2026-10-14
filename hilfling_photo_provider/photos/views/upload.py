import logging

from django.http import JsonResponse

from hilfling_photo_provider.utils.security_level import SecurityLevel

from .. import backend
from ..forms import PhotoUploadForm, UserUploadForm
from ..http import api_view, require_access, validated_data
from ..storage import PhotoFiles, build_filename, file_extension, image_url, user_content_path, write_user_content

logger = logging.getLogger(__name__)


def _photo_payload(data: dict) -> dict:
    payload = {
        "motiveId": str(data["motive_id"]),
        "dateTaken": data["date"].isoformat(),
        "goodPicture": bool(data.get("good_picture", False)),
        "mediaId": str(data["media_id"]),
    }
    if data.get("gang_id"):
        payload["gangId"] = str(data["gang_id"])
    return payload


@api_view("POST")
def photo_upload_view(request):
    logger.info("Upload request received")
    data = validated_data(PhotoUploadForm(request.POST, request.FILES), "photo upload")
    image_file = data["media"]
    security_level = data["security_level"]
    logger.info(
        "photo upload: file=%s size=%s security_level=%s motive_id=%s",
        image_file.name,
        image_file.size,
        security_level,
        data["motive_id"],
    )

    payload = _photo_payload(data)
    reservation = backend.reserve_photo(request, payload)
    page_number = reservation["pageNumber"]
    image_number = reservation["imageNumber"]

    album = reservation["album"]["name"]
    filename = build_filename(album, page_number, image_number, file_extension(image_file.name))
    files = PhotoFiles.for_photo(security_level, album, filename)
    urls = files.urls

    try:
        files.write(image_file.read())
        backend.finalize_photo(
            request,
            {
                **payload,
                "securityLevel": security_level,
                "pageNumber": page_number,
                "imageNumber": image_number,
                "imageProd": urls["prod"],
                "imageWeb": urls["web"],
                "imageThumb": urls["thumb"],
            },
        )
    except Exception:
        files.delete()
        raise

    logger.info("photo upload stored: %s", files.rels)
    return JsonResponse({"ok": True, **urls}, status=201)


@api_view("POST")
def user_upload_view(request):
    """Accept a user content upload, store it, and register it in the backend.

    The file is stored under user-content/<security_level>/<uuid>.<ext> and the
    backend is updated with the resulting link so the upload is tied to the
    uploading user. User content is gated by the uploader's permission (FG
    membership) and its security level can only be ALLE or FG, never HUSFOLK.
    """
    # The backend re-checks FG membership when registering the upload.
    require_access(request, SecurityLevel.FG)

    data = validated_data(UserUploadForm(request.POST, request.FILES), "user upload")
    image_file = data["media"]
    security_level = data["security_level"]
    logger.info("user upload: file=%s size=%s security_level=%s", image_file.name, image_file.size, security_level)

    rel_path = user_content_path(security_level, file_extension(image_file.name))
    abs_path = write_user_content(rel_path, image_file.read())
    link = image_url(rel_path)

    try:
        registered = backend.register_user_upload(request, link, security_level)
    except Exception:
        abs_path.unlink(missing_ok=True)
        raise

    logger.info("user upload stored: %s", rel_path)
    return JsonResponse({"ok": True, "link": link, "userUpload": registered}, status=201)

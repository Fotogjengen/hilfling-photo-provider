"""Client for the main backend, authenticated with the caller's own token."""

import logging

import requests
from django.conf import settings

from .http import ApiError

logger = logging.getLogger(__name__)

TIMEOUT_SECONDS = 10
LOG_BODY_LIMIT = 2000


class BackendUnavailable(ApiError):
    def __init__(self):
        super().__init__("Backend unavailable", 502)


class BackendRejected(ApiError):
    """The backend answered with an error; its status and body are passed on unchanged."""


def _post(request, path: str, payload: dict, label: str, ok_statuses: tuple[int, ...]) -> requests.Response:
    headers = {}
    token = request.COOKIES.get("fgToken")
    if token:
        headers["X-hilfling-token"] = token

    try:
        resp = requests.post(f"{settings.PROXY_TARGET_URL}{path}", json=payload, headers=headers, timeout=TIMEOUT_SECONDS)
    except requests.RequestException:
        logger.exception("%s request to backend failed", label)
        raise BackendUnavailable()

    if resp.status_code not in ok_statuses:
        logger.warning("%s rejected: HTTP %s body=%s", label, resp.status_code, resp.text[:LOG_BODY_LIMIT])
        try:
            body = resp.json()
        except ValueError:
            body = {"error": resp.text}
        raise BackendRejected(body, resp.status_code)
    return resp


def reserve_photo(request, payload: dict) -> dict:
    """Reserve an image slot (album, page and image number) before anything is written to disk."""
    return _post(request, "/photos/upload/reserve", payload, "reserve", (200,)).json()


def finalize_photo(request, payload: dict) -> None:
    _post(request, "/photos/upload/finalize", payload, "finalize", (200, 201))


def register_user_upload(request, link: str, security_level: str) -> dict:
    payload = {"link": link, "securityLevel": {"securityLevelType": security_level}}
    return _post(request, "/user-uploads", payload, "user upload register", (200, 201)).json()

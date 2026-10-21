import logging
from functools import wraps

from django.http import JsonResponse

from hilfling_photo_provider.utils.auth import InvalidToken, can_access, can_access_prod, verify_service_request

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Raised anywhere inside an api_view to end the request with a JSON error response."""

    def __init__(self, body: dict | str, status: int):
        super().__init__(body)
        self.body = {"error": body} if isinstance(body, str) else body
        self.status = status


def api_view(*methods: str):
    """Restrict a view to the given HTTP methods and turn ApiError into a JSON response."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method not in methods:
                return JsonResponse({"error": "Method not allowed"}, status=405)
            try:
                return view(request, *args, **kwargs)
            except ApiError as exc:
                return JsonResponse(exc.body, status=exc.status, safe=False)

        return wrapper

    return decorator


def service_scope(scope: str):
    """Require a backend service token for the given scope (see verify_service_request)."""

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            try:
                verify_service_request(request, scope)
            except InvalidToken:
                raise ApiError("Invalid service token", 401)
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


def require_access(request, required_level: str, *, prod: bool = False) -> None:
    """Raise ApiError 401 for an invalid token, 403 when the token's level doesn't permit required_level."""
    check = can_access_prod if prod else can_access
    try:
        allowed = check(request, required_level)
    except InvalidToken:
        raise ApiError("Invalid token", 401)
    if not allowed:
        raise ApiError("Forbidden", 403)


def validated_data(form, label: str) -> dict:
    if not form.is_valid():
        logger.warning("%s rejected: %s", label, form.errors.as_json())
        raise ApiError({"error": "Invalid parameters", "field_errors": form.errors}, 400)
    return form.cleaned_data

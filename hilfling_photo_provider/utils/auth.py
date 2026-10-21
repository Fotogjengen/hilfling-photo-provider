"""Local JWT verification for image access control.

The proxy verifies the backend's JWTs locally using the backend's public key,
fetched once from its JWKS endpoint and cached (refetched automatically when an
unknown key id appears, e.g. after a key rotation). No shared secret, and no
per-request round trip to the backend.

Token semantics mirror the backend's JwtAuthFilter:
  * no token        -> anonymous, security level "ALLE" (public)
  * valid token     -> the token's securityLevel
  * invalid token   -> InvalidToken is raised (callers return 401); an expired,
                       tampered or otherwise broken token is never silently
                       downgraded to public access.
"""

import hashlib
import hmac
from functools import cache

import jwt
from django.conf import settings
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

from .security_level import SecurityLevel

# Which security levels a user of a given level may view
_ALLOWED_BY_LEVEL = {
    SecurityLevel.FG: {SecurityLevel.FG, SecurityLevel.HUSFOLK, SecurityLevel.ALLE},
    SecurityLevel.HUSFOLK: {SecurityLevel.HUSFOLK, SecurityLevel.ALLE},
}
_PUBLIC_ONLY = {SecurityLevel.ALLE}
_MEMBER_LEVELS = (SecurityLevel.FG, SecurityLevel.HUSFOLK)

# Service tokens: minted by the backend for its calls to our provider-internal endpoints
SERVICE_ISSUER = "hilfling-backend"
SERVICE_AUDIENCE = "photo-provider"


class InvalidToken(Exception):
    """Raised when a token is present but fails verification."""


@cache
def _jwks_client() -> PyJWKClient:
    return PyJWKClient(settings.JWKS_URL)


def _decode(token: str, **options) -> dict:
    try:
        signing_key = _jwks_client().get_signing_key_from_jwt(token)
        return jwt.decode(token, signing_key.key, algorithms=["RS256"], **options)
    except (InvalidTokenError, PyJWKClientError) as e:
        raise InvalidToken() from e


def _may_view(user_level: str, required_level: str) -> bool:
    return required_level.upper() in _ALLOWED_BY_LEVEL.get(user_level, _PUBLIC_ONLY)


def get_security_level(request) -> str:
    """Return the verified securityLevel, or "ALLE" when no token is present.

    Raises InvalidToken if a token is present but cannot be verified.
    """
    token = request.COOKIES.get("fgToken")
    if not token:
        return SecurityLevel.ALLE
    return _decode(token).get("securityLevel", SecurityLevel.ALLE)


def can_access(request, required_level: str) -> bool:
    """True if the request is allowed to view the given security level.

    Raises InvalidToken if a token is present but invalid.
    """
    return _may_view(get_security_level(request), required_level)


def can_access_prod(request, required_level: str) -> bool:
    """True if the request is allowed to view a prod-quality file.

    Prod files are members-only: an FG or HUSFOLK token is always required,
    so anonymous/ALLE users are denied even for photos whose security level
    is ALLE. The photo's own security level still applies on top of it.
    Metadata requests are exempt from this and keep using can_access.

    Raises InvalidToken if a token is present but invalid.
    """
    user_level = get_security_level(request)
    return user_level in _MEMBER_LEVELS and _may_view(user_level, required_level)


def verify_service_request(request, scope: str) -> None:
    """Raise InvalidToken unless the request carries a backend service token for this scope and this exact body.

    The token's planHash is the SHA-256 of the raw request body, so a captured token cannot be reused for a
    different payload. User tokens have no audience and are rejected.
    """
    header = request.headers.get("Authorization", "")
    if not header.startswith("Bearer "):
        raise InvalidToken()
    token = header.removeprefix("Bearer ").strip()

    claims = _decode(
        token,
        audience=SERVICE_AUDIENCE,
        issuer=SERVICE_ISSUER,
        options={"require": ["exp", "iat", "iss", "aud"]},
    )

    if claims.get("scope") != scope:
        raise InvalidToken()
    body_hash = hashlib.sha256(request.body).hexdigest()
    if not hmac.compare_digest(str(claims.get("planHash", "")), body_hash):
        raise InvalidToken()

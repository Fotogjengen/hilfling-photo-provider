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

import jwt
from django.conf import settings
from jwt import InvalidTokenError, PyJWKClient, PyJWKClientError

# JWKS client
_jwks_client = PyJWKClient(settings.JWKS_URL)

# Which security levels a user of a given level may view
_ALLOWED_BY_LEVEL = {
    "FG": {"FG", "HUSFOLK", "ALLE"},
    "HUSFOLK": {"HUSFOLK", "ALLE"},
}


class InvalidToken(Exception):
    """Raised when a token is present but fails verification."""


def get_security_level(request) -> str:
    """Return the verified securityLevel, or "ALLE" when no token is present.

    Raises InvalidToken if a token is present but cannot be verified.
    """
    token = request.COOKIES.get("fgToken")
    if not token:
        return "ALLE"

    try:
        signing_key = _jwks_client.get_signing_key_from_jwt(token)
        claims = jwt.decode(token, signing_key.key, algorithms=["RS256"])
    except (InvalidTokenError, PyJWKClientError) as e:
        raise InvalidToken() from e

    return claims.get("securityLevel", "ALLE")


def can_access(request, required_level: str) -> bool:
    """True if the request is allowed to view the given security level.

    Raises InvalidToken if a token is present but invalid.
    """
    user_level = get_security_level(request)
    return required_level.upper() in _ALLOWED_BY_LEVEL.get(user_level, {"ALLE"})

"""Security level lookup through ITK's ACLs (itkacl).

itkacl only exists on ITK's servers. In dev (DEBUG) a mock that reads realm members from settings.ITKACL_MOCK
stands in for it. Outside dev a missing itkacl raises, so lookups fail instead of resolving everyone to ALLE.

Realms mirror the old fg.samfundet.no KerberosBackend:
  * /web/fg   -> FG
  * /web/alle -> HUSFOLK
  * neither   -> ALLE
"""

import logging
from functools import cache

from django.conf import settings

from .security_level import SecurityLevel

logger = logging.getLogger(__name__)

# Checked in order, the first realm the user is in decides their level
_REALM_LEVELS = (
    ("/web/fg", SecurityLevel.FG),
    ("/web/alle", SecurityLevel.HUSFOLK),
)


class _MockItkacl:
    """Stand-in for itkacl's check(realm, username), backed by settings.ITKACL_MOCK ({realm: [usernames]})."""

    def __init__(self, realms: dict[str, list[str]]):
        self._realms = {realm: set(usernames) for realm, usernames in realms.items()}

    def check(self, realm: str, username: str) -> bool:
        return username in self._realms.get(realm, ())


@cache
def load_itkacl():
    """Return itkacl, or the mock in dev where it isn't installed. Raises ImportError outside dev."""
    try:
        import itkacl
    except ImportError:
        if not settings.DEBUG:
            raise
        logger.info("itkacl not installed, using the mock from settings.ITKACL_MOCK")
        return _MockItkacl(settings.ITKACL_MOCK)
    return itkacl


def security_level_for(username: str) -> str:
    """Return the security level ITK's ACLs give this username."""
    acl = load_itkacl()
    for realm, level in _REALM_LEVELS:
        if acl.check(realm, username):
            return level
    return SecurityLevel.ALLE

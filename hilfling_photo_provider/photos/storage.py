"""Layout of stored files.

Photos live under <security_level>/<quality>/<ALBUM>/<file>, user uploads under
user-content/<security_level>/<file>.
"""

import logging
import os
import re
import unicodedata
import uuid
from dataclasses import dataclass
from pathlib import Path

from django.conf import settings
from django.utils._os import safe_join

from hilfling_photo_provider.utils.security_level import SecurityLevel

from .imaging import save_thumb, save_web

logger = logging.getLogger(__name__)

QUALITIES = ("prod", "web", "thumb")
USER_CONTENT_DIR = "user-content"
DEFAULT_EXTENSION = "jpg"
MAX_EXTENSION_LENGTH = 8

_SECURITY_DIRS = [level.lower() for level in SecurityLevel.values]
_STORED_PATH = re.compile(
    rf"^({'|'.join(_SECURITY_DIRS)})/({'|'.join(QUALITIES)})/[A-Za-z0-9_-]+/[A-Za-z0-9_-]+\.[A-Za-z0-9]+$"
)


class RelocationConflict(Exception):
    """A file cannot be moved without losing data (missing source or occupied destination)."""


def slugify(name: str) -> str:
    """Convert a string to a filesystem/URL-safe slug (ASCII, no spaces)."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    return re.sub(r"[^a-zA-Z0-9_-]+", "_", ascii_name).strip("_")


def file_extension(filename: str) -> str:
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else DEFAULT_EXTENSION
    return re.sub(r"[^a-z0-9]", "", ext)[:MAX_EXTENSION_LENGTH] or DEFAULT_EXTENSION


def build_filename(album: str, page_number: int, image_number: int, ext: str) -> str:
    return f"{slugify(album).lower()}{page_number:02d}{image_number:02d}.{ext}"


def relative_path(security_level: str, quality: str, album: str, filename: str) -> str:
    return f"{security_level.lower()}/{quality}/{slugify(album).upper()}/{filename}"


def user_content_path(security_level: str, ext: str) -> str:
    return f"{USER_CONTENT_DIR}/{security_level.lower()}/{uuid.uuid4()}.{ext}"


def storage_path(rel: str) -> Path:
    """Absolute path of a storage-relative path. Raises ValueError/SuspiciousFileOperation if it escapes storage."""
    return Path(safe_join(settings.IMAGE_STORAGE_PATH, rel))


def image_url(rel: str) -> str:
    return f"{settings.IMAGE_BASE_URL.rstrip('/')}/{rel}"


def write_user_content(rel: str, data: bytes) -> Path:
    path = storage_path(rel)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@dataclass(frozen=True)
class StoredPath:
    """What a request path says about the file: its security level and whether it is a prod-quality photo."""

    level: str
    quality: str | None

    @classmethod
    def parse(cls, path: str) -> "StoredPath":
        segments = path.strip("/").split("/")
        if segments[0].lower() == USER_CONTENT_DIR:
            return cls(level=segments[1].upper() if len(segments) > 1 else "", quality=None)
        return cls(level=segments[0].upper(), quality=segments[1].lower() if len(segments) > 1 else None)

    @property
    def is_prod(self) -> bool:
        return self.quality == "prod"


def stored_rel(url: str | None) -> str | None:
    """Storage-relative path of an image URL we serve, or None for URLs we don't serve (e.g. external mock data)."""
    base = settings.IMAGE_BASE_URL.rstrip("/")
    if not url or not url.startswith(base + "/"):
        return None
    rel = url[len(base):].lstrip("/")
    return rel if _STORED_PATH.match(rel) else None


def valid_stored_path(rel: str) -> bool:
    return bool(_STORED_PATH.match(rel))


@dataclass(frozen=True)
class PhotoFiles:
    """The prod, web and thumb files of one photo."""

    rels: dict[str, str]

    @classmethod
    def for_photo(cls, security_level: str, album: str, filename: str) -> "PhotoFiles":
        return cls({quality: relative_path(security_level, quality, album, filename) for quality in QUALITIES})

    @property
    def urls(self) -> dict[str, str]:
        return {quality: image_url(rel) for quality, rel in self.rels.items()}

    def write(self, image_data: bytes) -> None:
        paths = {quality: storage_path(rel) for quality, rel in self.rels.items()}
        for path in paths.values():
            path.parent.mkdir(parents=True, exist_ok=True)
        paths["prod"].write_bytes(image_data)
        save_web(image_data, paths["web"])
        save_thumb(image_data, paths["thumb"])

    def delete(self) -> None:
        for rel in self.rels.values():
            storage_path(rel).unlink(missing_ok=True)


def move_file(src_rel: str, dst_rel: str) -> tuple[Path, Path] | None:
    """Move a file without overwriting. Returns (dst, src) when a file moved, None when it was already in place.

    If the source is missing, the same file under another security level is used, which recovers from an earlier
    relocation whose DB commit failed.
    """
    dst = storage_path(dst_rel)
    src = storage_path(src_rel)
    if not src.is_file():
        if dst.is_file():
            return None
        _, rest = src_rel.split("/", 1)
        siblings = (storage_path(f"{level}/{rest}") for level in _SECURITY_DIRS)
        src = next((p for p in siblings if p.is_file() and p != dst), None)
        if src is None:
            raise RelocationConflict(f"{src_rel} not found")
    if dst.exists():
        raise RelocationConflict(f"{dst_rel} already exists")
    dst.parent.mkdir(parents=True, exist_ok=True)
    os.link(src, dst)
    os.unlink(src)
    return dst, src


def undo_moves(moved: list[tuple[Path, Path]]) -> None:
    for dst, src in reversed(moved):
        try:
            os.link(dst, src)
            os.unlink(dst)
        except OSError:
            logger.exception("rollback of %s -> %s failed", src, dst)

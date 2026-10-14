from .base import *

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
PROXY_TARGET_URL = "http://localhost:8000/api"
JWKS_URL = f"{PROXY_TARGET_URL}/.well-known/jwks.json"

IMAGE_STORAGE_PATH = str(BASE_DIR / "media")
IMAGE_BASE_URL = "/media"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
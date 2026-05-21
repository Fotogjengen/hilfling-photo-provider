from .base import *

DEBUG = True
MOCK_LOGIN = True
ENABLE_PROXY = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]
CORS_ALLOWED_ORIGINS = ["http://localhost:3000"]
PROXY_TARGET_URL = "http://localhost:8000"

IMAGE_STORAGE_PATH = str(BASE_DIR / "media")
IMAGE_BASE_URL = "http://localhost:8888/media"
MEDIA_ROOT = BASE_DIR / "media"
MEDIA_URL = "/media/"
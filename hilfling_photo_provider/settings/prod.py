from .base import *

DEBUG = False
ALLOWED_HOSTS = ["foto.samfundet.no", "localhost"]
PROXY_TARGET_URL = "https://hilfling-app.norwayeast.cloudapp.azure.com/api"
JWKS_URL = f"{PROXY_TARGET_URL}/.well-known/jwks.json"
IMAGE_STORAGE_PATH = str(BASE_DIR / "media")
IMAGE_BASE_URL = "/media"
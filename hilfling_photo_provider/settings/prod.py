from .base import *

DEBUG = False
ALLOWED_HOSTS = ["arim-fg.samfundet.no", "localhost"]  #Hard-coded for testing, remove later
PROXY_TARGET_URL="https://hilfling-app.norwayeast.cloudapp.azure.com/api"
JWKS_URL = f"{PROXY_TARGET_URL}/.well-known/jwks.json"
IMAGE_STORAGE_PATH = str(BASE_DIR / "media")
IMAGE_BASE_URL = "/media"
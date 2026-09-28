from .base import *

DEBUG = False
ALLOWED_HOSTS = ["arim-fg.samfundet.no", "localhost"]  #Hard-coded for testing, remove later
PROXY_TARGET_URL="https://arim-fg.samfundet.no/api"
JWKS_URL = f"{PROXY_TARGET_URL}/.well-known/jwks.json"
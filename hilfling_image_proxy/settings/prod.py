from .base import *

DEBUG = False
ALLOWED_HOSTS = ["arim-fg.samfundet.no", "localhost"]  #Hard-coded for testing, remove later

#lets try logging env ig
import os, sys
print(
    f"[prod settings] DEBUG={DEBUG} ALLOWED_HOSTS={ALLOWED_HOSTS!r} "
    f"raw_env={os.environ.get('ALLOWED_HOSTS')!r}",
    file=sys.stderr, flush=True,
)
#!/usr/bin/env python
"""Django's command-line utility for administrative tasks."""
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "hilfling_image_proxy.settings.dev")

def main():
    """Run administrative tasks."""
    os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'hilfling_image_proxy.settings')
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Couldn't import Django. Are you sure it's installed and "
            "available on your PYTHONPATH environment variable? Did you "
            "forget to activate a virtual environment?"
        ) from exc
    execute_from_command_line(sys.argv)


import os
import sys
from pathlib import Path
import environ

env = environ.Env()
environ.Env.read_env(Path(__file__).resolve().parent / ".env")

if __name__ == "__main__":
    from django.core.management import execute_from_command_line
    args = sys.argv
    if len(args) == 2 and args[1] == "runserver":
        args.append(f"127.0.0.1:{env('DJANGO_PORT', default='8888')}")
    execute_from_command_line(args)
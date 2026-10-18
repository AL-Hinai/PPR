"""Test settings: in-memory SQLite and a throwaway media folder."""
import tempfile
from pathlib import Path

from .base import *  # noqa: F401,F403

DEBUG = False
ALLOWED_HOSTS = ["testserver"]
DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": ":memory:"}}
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
MEDIA_ROOT = Path(tempfile.mkdtemp(prefix="ppr-test-media-"))
# Workflow tests drive assignment explicitly; tests of automatic assignment switch it on.
AUTO_ASSIGN_REVIEW_TEAMS = False

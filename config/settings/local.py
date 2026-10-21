"""Local development: SQLite, debug on, live reload."""
from .base import *  # noqa: F401,F403
from .base import BASE_DIR, INSTALLED_APPS, MIDDLEWARE, env

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1", "[::1]"]

# One-click sign-in as each demo account, so the workflow can be tried from every role.
DEMO_LOGIN = env.bool("DEMO_LOGIN", default=True)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": BASE_DIR / "db.sqlite3",
    }
}

INSTALLED_APPS = [*INSTALLED_APPS, "django_browser_reload"]
MIDDLEWARE = [*MIDDLEWARE, "django_browser_reload.middleware.BrowserReloadMiddleware"]

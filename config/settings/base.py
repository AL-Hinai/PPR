"""Settings shared by every environment."""
from pathlib import Path

import environ
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = False
ALLOWED_HOSTS: list[str] = []

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "django_htmx",
    "tailwind",
    "theme",
    "apps.core",
    "apps.accounts",
    "apps.companies",
    "apps.applications",
    "apps.validation",
    "apps.notifications",
    "apps.assistant",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.locale.LocaleMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.notifications.context_processors.notifications",
                "apps.assistant.context_processors.assistant",
            ],
        },
    },
]

AUTH_USER_MODEL = "accounts.User"
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

# Internationalisation: English + Arabic (RTL)
LANGUAGE_CODE = "en"
LANGUAGES = [("en", _("English")), ("ar", _("Arabic"))]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "Asia/Muscat"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Uploaded dossiers are private: MEDIA_ROOT is never mapped to a public URL.
# Files are streamed through permission-checked views instead.
MEDIA_ROOT = Path(env("MEDIA_ROOT", default=str(BASE_DIR / "private_media")))
FILE_UPLOAD_PERMISSIONS = 0o640

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

EMAIL_BACKEND = env("EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="PPR <no-reply@localhost>")

# Tailwind: standalone CLI binary (no Node.js required)
TAILWIND_APP_NAME = "theme"
TAILWIND_USE_STANDALONE_BINARY = True

# eCTD technical validation
ECTD_REGION = env("ECTD_REGION", default="gcc")
ECTD_DTD_PATH = env(
    "ECTD_DTD_PATH", default=str(BASE_DIR / "apps" / "validation" / "dtd" / "ich-ectd-3-2.dtd")
)
ECTD_MAX_UPLOAD_MB = env.int("ECTD_MAX_UPLOAD_MB", default=500)
ECTD_MAX_UNCOMPRESSED_MB = env.int("ECTD_MAX_UNCOMPRESSED_MB", default=1024)
ECTD_MAX_FILES = env.int("ECTD_MAX_FILES", default=5000)
ECTD_MAX_FILE_MB = env.int("ECTD_MAX_FILE_MB", default=400)
# Findings reported per rule before the rest are summarised in one line.
ECTD_MAX_FINDINGS_PER_RULE = 50

# Dossier assistant (ported from Roaa). Any OpenAI-compatible chat API; DeepSeek by default.
# With no API key the assistant runs in offline mode (search results, no written answer).
ASSISTANT = {
    "PROVIDER": env("ASSISTANT_PROVIDER", default="openai"),  # openai | offline
    "API_KEY": env("ASSISTANT_API_KEY", default=""),
    "BASE_URL": env("ASSISTANT_BASE_URL", default="https://api.deepseek.com/v1"),
    "MODEL": env("ASSISTANT_MODEL", default="deepseek-v4-pro"),
    "TIMEOUT": env.float("ASSISTANT_TIMEOUT", default=60),
    "TEMPERATURE": env.float("ASSISTANT_TEMPERATURE", default=0.2),
    "MAX_STEPS": env.int("ASSISTANT_MAX_STEPS", default=8),
    "DEADLINE_SECONDS": env.int("ASSISTANT_DEADLINE_SECONDS", default=150),
}

# Approval validity in years (printed on the certificate)
APPROVAL_VALIDITY_YEARS = env.int("APPROVAL_VALIDITY_YEARS", default=5)

# Assign the review team from reviewer specialties as soon as an application passes validation.
# Off: the HOD assigns every team by hand from the dashboard.
AUTO_ASSIGN_REVIEW_TEAMS = env.bool("AUTO_ASSIGN_REVIEW_TEAMS", default=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"apps": {"handlers": ["console"], "level": "INFO"}},
}

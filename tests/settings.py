from __future__ import annotations

from typing import Any

SECRET_KEY = "NOTASECRET"

ALLOWED_HOSTS: list[str] = []

DATABASES: dict[str, dict[str, Any]] = {}

INSTALLED_APPS = [
    "tests",
    "django_http_compression",
]

MIDDLEWARE = [
    "django_http_compression.middleware.HttpCompressionMiddleware",
]

ROOT_URLCONF = "tests.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "OPTIONS": {"context_processors": []},
    }
]

USE_TZ = True

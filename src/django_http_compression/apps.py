from __future__ import annotations

from django.apps import AppConfig
from django.core.checks import Tags, register

from django_http_compression.checks import check_settings


class DjangoHttpCompressionAppConfig(AppConfig):
    name = "django_http_compression"
    verbose_name = "django-http-compression"

    def ready(self) -> None:
        register(Tags.security)(check_settings)

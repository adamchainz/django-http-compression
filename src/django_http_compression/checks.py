from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage
from django.core.checks import Warning as CheckWarning


def check_settings(**kwargs: Any) -> list[CheckMessage]:
    errors: list[CheckMessage] = []

    using_compression_middleware = False
    conflicts = set()

    for value in settings.MIDDLEWARE:
        if value == "django_http_compression.middleware.CompressionMiddleware":
            using_compression_middleware = True
        elif value in (
            "django.middleware.gzip.GZipMiddleware",
            # From legacy package django-compression-middleware:
            # https://pypi.org/project/django-compression-middleware/
            "compression_middleware.middleware.CompressionMiddleware",
        ):
            conflicts.add(value)

    if using_compression_middleware and conflicts:
        for conflict in conflicts:
            errors.append(
                CheckWarning(
                    f"Using 'django_http_compression.middleware.CompressionMiddleware' and {conflict!r} together may prevent optimal compression.",
                    hint=f"Remove {conflict!r} from the MIDDLEWARE setting.",
                    id="django_http_compression.W001",
                )
            )

    return errors

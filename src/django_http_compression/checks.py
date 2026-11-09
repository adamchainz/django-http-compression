from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage
from django.core.checks import Warning as CheckWarning
from django.utils.module_loading import import_string


def check_settings(**kwargs: Any) -> list[CheckMessage]:
    errors: list[CheckMessage] = []

    compression_middleware = None
    conflicts = set()

    for value in settings.MIDDLEWARE:
        if value == "django_http_compression.middleware.HttpCompressionMiddleware":
            compression_middleware = value
        elif value in (
            "django.middleware.gzip.GZipMiddleware",
            # From legacy package django-compression-middleware:
            # https://pypi.org/project/django-compression-middleware/
            "compression_middleware.middleware.CompressionMiddleware",
        ):
            conflicts.add(value)

    if compression_middleware is None and conflicts:
        compression_middleware = _find_subclass(settings.MIDDLEWARE)

    if compression_middleware is not None:
        for conflict in conflicts:
            errors.append(
                CheckWarning(
                    f"Using {compression_middleware!r} and {conflict!r} together may prevent optimal compression.",
                    hint=f"Remove {conflict!r} from the MIDDLEWARE setting.",
                    id="django_http_compression.W001",
                )
            )

    return errors


def _find_subclass(middleware: Sequence[str]) -> str | None:
    """
    Return the first MIDDLEWARE entry that subclasses HttpCompressionMiddleware,
    as used to change compression levels. This requires importing the
    entries, so it’s only done when a conflict is found.
    """
    from django_http_compression.middleware import HttpCompressionMiddleware

    for value in middleware:
        try:
            cls = import_string(value)
        except ImportError:
            continue
        if isinstance(cls, type) and issubclass(cls, HttpCompressionMiddleware):
            return value
    return None

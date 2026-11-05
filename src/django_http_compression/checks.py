from __future__ import annotations

from typing import Any

from django.conf import settings
from django.core.checks import CheckMessage
from django.core.checks import Warning as CheckWarning
from django.utils.module_loading import import_string

COMPRESSION_MIDDLEWARE = "django_http_compression.middleware.HttpCompressionMiddleware"

CONFLICTING_MIDDLEWARE = (
    "django.middleware.gzip.GZipMiddleware",
    # From legacy package django-compression-middleware:
    # https://pypi.org/project/django-compression-middleware/
    "compression_middleware.middleware.CompressionMiddleware",
)


def check_settings(**kwargs: Any) -> list[CheckMessage]:
    middleware = list(dict.fromkeys(settings.MIDDLEWARE))

    # Match exact paths first, and only import to find subclasses when needed,
    # since importing may be expensive.
    compression_middleware: str | None = None
    if COMPRESSION_MIDDLEWARE in middleware:
        compression_middleware = COMPRESSION_MIDDLEWARE
    else:
        compression_base = import_string(COMPRESSION_MIDDLEWARE)
        for value in middleware:
            if _is_subclass(value, compression_base):
                compression_middleware = value
                break

    if compression_middleware is None:
        return []

    conflicts = {value for value in middleware if value in CONFLICTING_MIDDLEWARE}
    remaining = [
        value
        for value in middleware
        if value != compression_middleware and value not in conflicts
    ]
    if remaining:
        conflict_bases = tuple(
            base
            for path in CONFLICTING_MIDDLEWARE
            if (base := _import_class(path)) is not None
        )
        conflicts.update(
            value for value in remaining if _is_subclass(value, conflict_bases)
        )

    return [
        CheckWarning(
            f"Using {compression_middleware!r} and {conflict!r} together may prevent optimal compression.",
            hint=f"Remove {conflict!r} from the MIDDLEWARE setting.",
            id="django_http_compression.W001",
        )
        # Report in MIDDLEWARE order.
        for conflict in middleware
        if conflict in conflicts
    ]


def _import_class(path: str) -> type | None:
    try:
        imported = import_string(path)
    except ImportError:
        return None
    return imported if isinstance(imported, type) else None


def _is_subclass(value: str, base: type | tuple[type, ...]) -> bool:
    cls = _import_class(value)
    return cls is not None and issubclass(cls, base)

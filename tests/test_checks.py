from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase
from django.test.utils import override_settings

from django_http_compression.checks import check_settings


class ChecksTests(SimpleTestCase):
    def test_defaults_pass(self):
        messages = check_settings()
        assert messages == []

    def test_defaults_pass_check(self):
        call_command("check")

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.CompressionMiddleware",
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_checks_are_bound(self):
        err = StringIO()
        call_command("check", stderr=err)
        assert "django_http_compression.W001" in err.getvalue()

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.CompressionMiddleware",
        ]
    )
    def test_e001_just_compression_middleware(self):
        messages = check_settings()
        assert messages == []

    @override_settings(
        MIDDLEWARE=[
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_e001_just_gzip_middleware(self):
        messages = check_settings()
        assert messages == []

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.CompressionMiddleware",
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_e001_conflict_gzip(self):
        messages = check_settings()
        assert len(messages) == 1
        assert messages[0].id == "django_http_compression.W001"
        assert "GZipMiddleware" in messages[0].msg

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.CompressionMiddleware",
            "compression_middleware.middleware.CompressionMiddleware",
        ]
    )
    def test_e001_conflict_old_package(self):
        messages = check_settings()
        assert len(messages) == 1
        assert messages[0].id == "django_http_compression.W001"
        assert "compression_middleware" in messages[0].msg

from __future__ import annotations

from io import StringIO
from typing import Any
from unittest import mock

from django.core.management import call_command
from django.middleware.gzip import GZipMiddleware
from django.test import SimpleTestCase
from django.test.utils import override_settings
from django.utils.module_loading import import_string

from django_http_compression.checks import check_settings
from django_http_compression.middleware import HttpCompressionMiddleware


class CompressionMiddlewareSubclass(HttpCompressionMiddleware):
    pass


class GZipMiddlewareSubclass(GZipMiddleware):
    pass


def function_middleware(get_response):  # pragma: no cover
    return get_response


class ChecksTests(SimpleTestCase):
    def test_defaults_pass(self):
        messages = check_settings()
        assert messages == []

    def test_defaults_pass_check(self):
        call_command("check")

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.HttpCompressionMiddleware",
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_checks_are_bound(self):
        err = StringIO()
        call_command("check", stderr=err)
        assert "django_http_compression.W001" in err.getvalue()

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.HttpCompressionMiddleware",
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
            "django_http_compression.middleware.HttpCompressionMiddleware",
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
            "django_http_compression.middleware.HttpCompressionMiddleware",
            "compression_middleware.middleware.CompressionMiddleware",
        ]
    )
    def test_e001_conflict_old_package(self):
        messages = check_settings()
        assert len(messages) == 1
        assert messages[0].id == "django_http_compression.W001"
        assert "compression_middleware" in messages[0].msg

    @override_settings(
        MIDDLEWARE=[
            "tests.test_checks.CompressionMiddlewareSubclass",
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_e001_conflict_compression_subclass(self):
        messages = check_settings()
        assert len(messages) == 1
        assert messages[0].id == "django_http_compression.W001"
        assert "tests.test_checks.CompressionMiddlewareSubclass" in messages[0].msg
        assert "GZipMiddleware" in messages[0].msg

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.HttpCompressionMiddleware",
            "tests.test_checks.GZipMiddlewareSubclass",
        ]
    )
    def test_e001_conflict_gzip_subclass(self):
        messages = check_settings()
        assert len(messages) == 1
        assert messages[0].id == "django_http_compression.W001"
        assert "tests.test_checks.GZipMiddlewareSubclass" in messages[0].msg

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.HttpCompressionMiddleware",
            "django.middleware.gzip.GZipMiddleware",
            "compression_middleware.middleware.CompressionMiddleware",
        ]
    )
    def test_e001_conflict_multiple(self):
        messages = check_settings()
        assert len(messages) == 2
        assert "GZipMiddleware" in messages[0].msg
        assert "compression_middleware" in messages[1].msg

    @override_settings(
        MIDDLEWARE=[
            "tests.test_checks.CompressionMiddlewareSubclass",
            "django.middleware.common.CommonMiddleware",
            "nonexistent.middleware.Middleware",
        ]
    )
    def test_e001_no_conflict_other_middleware(self):
        messages = check_settings()
        assert messages == []

    @override_settings(
        MIDDLEWARE=[
            "tests.test_checks.CompressionMiddlewareSubclass",
            "tests.test_checks.function_middleware",
        ]
    )
    def test_e001_no_conflict_function_middleware(self):
        messages = check_settings()
        assert messages == []

    def mock_import_string(self) -> Any:
        return mock.patch(
            "django_http_compression.checks.import_string", wraps=import_string
        )

    @override_settings(
        MIDDLEWARE=[
            "django_http_compression.middleware.HttpCompressionMiddleware",
        ]
    )
    def test_e001_exact_path_no_import(self):
        with self.mock_import_string() as mocked:
            messages = check_settings()

        assert messages == []
        mocked.assert_not_called()

    @override_settings(
        MIDDLEWARE=[
            "django.middleware.gzip.GZipMiddleware",
            "django_http_compression.middleware.HttpCompressionMiddleware",
        ]
    )
    def test_e001_exact_paths_conflict_no_import(self):
        with self.mock_import_string() as mocked:
            messages = check_settings()

        assert len(messages) == 1
        mocked.assert_not_called()

    @override_settings(
        MIDDLEWARE=[
            "django.middleware.common.CommonMiddleware",
            "django.middleware.gzip.GZipMiddleware",
        ]
    )
    def test_e001_no_compression_middleware_skips_conflict_imports(self):
        with self.mock_import_string() as mocked:
            messages = check_settings()

        assert messages == []
        imported = [call.args[0] for call in mocked.call_args_list]
        assert imported == [
            "django_http_compression.middleware.HttpCompressionMiddleware",
            "django.middleware.common.CommonMiddleware",
            "django.middleware.gzip.GZipMiddleware",
        ]

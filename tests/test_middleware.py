from __future__ import annotations

import gzip
import inspect
import sys
import zlib
from collections.abc import Iterator
from gzip import decompress as gzip_decompress
from http import HTTPStatus
from textwrap import dedent
from typing import cast

import django
import pytest
from brotli import Decompressor as BrotliDecompressor
from brotli import decompress as brotli_decompress
from django.http import StreamingHttpResponse
from django.middleware import gzip as django_middleware_gzip
from django.test import SimpleTestCase
from unittest_parametrize import ParametrizedTestCase, parametrize

from django_http_compression.middleware import best_coding
from tests.views import basic_html


class HttpCompressionMiddlewareTests(SimpleTestCase):
    def test_short(self):
        response = self.client.get("/short/", headers={"accept-encoding": "gzip"})

        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        assert response.content == b"short"

    def test_encoded(self):
        response = self.client.get("/encoded/", headers={"accept-encoding": "gzip"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "supercompression"
        assert "vary" not in response.headers
        assert response.content.decode() == basic_html

    def test_identity(self):
        response = self.client.get("/")

        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        assert response.content.decode() == basic_html

    def test_gzip(self):
        response = self.client.get("/", headers={"accept-encoding": "gzip"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip_decompress(response.content)
        assert decompressed.decode() == basic_html

    def test_brotli(self):
        response = self.client.get("/", headers={"accept-encoding": "br"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"\x1b]\x01\x00")
        decompressed = brotli_decompress(response.content)
        assert decompressed.decode() == basic_html

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    def test_zstd(self):
        from compression.zstd import decompress

        response = self.client.get("/", headers={"accept-encoding": "zstd"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"(\xb5/\xfd")
        decompressed = decompress(response.content)
        assert decompressed.decode() == basic_html

    def test_streaming_identity(self):
        response = self.client.get("/streaming/")

        assert isinstance(response, StreamingHttpResponse)
        assert not response.is_async
        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        streaming_content = cast(Iterator[bytes], response.streaming_content)
        content = next(streaming_content)
        assert content == b"<!doctype html>\n"
        content += next(streaming_content)
        assert content == b"<!doctype html>\n<html>\n"
        for chunk in streaming_content:
            content += chunk
        assert content.decode() == basic_html

    def test_streaming_gzip(self):
        response = self.client.get("/streaming/", headers={"accept-encoding": "gzip"})

        assert isinstance(response, StreamingHttpResponse)
        assert not response.is_async
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"

        decompressor = zlib.decompressobj(zlib.MAX_WBITS | 16)  # gzip decoding
        content = b""
        streaming_content = cast(Iterator[bytes], response.streaming_content)

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b""
        content += decompressed

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b"<!doctype html>\n"
        content += decompressed

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b"<html>\n"
        content += decompressed

        for chunk in streaming_content:
            content += decompressor.decompress(chunk)
        content += decompressor.flush()

        assert content.decode() == basic_html

    def test_streaming_brotli(self):
        response = self.client.get("/streaming/", headers={"accept-encoding": "br"})

        assert isinstance(response, StreamingHttpResponse)
        assert not response.is_async
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"

        streaming_content = cast(Iterator[bytes], response.streaming_content)
        decompressor = BrotliDecompressor()
        content = b""

        decompressed = decompressor.process(next(streaming_content))
        assert decompressed == b""
        content += decompressed

        decompressed = decompressor.process(next(streaming_content))
        assert decompressed == b"<!doctype html>\n"
        content += decompressed

        decompressed = decompressor.process(next(streaming_content))
        assert decompressed == b"<html>\n"
        content += decompressed

        for chunk in streaming_content:
            content += decompressor.process(chunk)

        assert content.decode() == basic_html
        assert decompressor.is_finished()

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    def test_streaming_zstd(self):
        from compression.zstd import ZstdDecompressor

        response = self.client.get("/streaming/", headers={"accept-encoding": "zstd"})

        assert isinstance(response, StreamingHttpResponse)
        assert not response.is_async
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"

        streaming_content = cast(Iterator[bytes], response.streaming_content)
        decompressor = ZstdDecompressor()
        content = b""

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b""
        content += decompressed

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b"<!doctype html>\n"
        content += decompressed

        decompressed = decompressor.decompress(next(streaming_content))
        assert decompressed == b"<html>\n"
        content += decompressed

        for chunk in streaming_content:
            content += decompressor.decompress(chunk)

        assert decompressor.eof
        assert decompressor.unused_data == b""
        assert content.decode() == basic_html

    def test_streaming_empty_identity(self):
        response = self.client.get("/streaming/empty/")

        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        content = response.getvalue()
        assert content == b""

    def test_streaming_empty_gzip(self):
        response = self.client.get(
            "/streaming/empty/", headers={"accept-encoding": "gzip"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip.decompress(content)
        assert decompressed == b""

    def test_streaming_empty_brotli(self):
        response = self.client.get(
            "/streaming/empty/", headers={"accept-encoding": "br"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content == b";"
        decompressed = brotli_decompress(content)
        assert decompressed == b""

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    def test_streaming_empty_zstd(self):
        from compression.zstd import decompress

        response = self.client.get(
            "/streaming/empty/", headers={"accept-encoding": "zstd"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content.startswith(b"(\xb5/\xfd")
        decompressed = decompress(content)
        assert decompressed == b""

    def test_streaming_blanks_identity(self):
        response = self.client.get("/streaming/blanks/")

        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        content = response.getvalue()
        assert content == b""

    def test_streaming_blanks_gzip(self):
        response = self.client.get(
            "/streaming/blanks/", headers={"accept-encoding": "gzip"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip.decompress(content)
        assert decompressed == b""

    def test_streaming_blanks_brotli(self):
        response = self.client.get(
            "/streaming/blanks/", headers={"accept-encoding": "br"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content == b"k\x00\x03"
        decompressed = brotli_decompress(content)
        assert decompressed == b""

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    def test_streaming_blanks_zstd(self):
        from compression.zstd import decompress

        response = self.client.get(
            "/streaming/blanks/", headers={"accept-encoding": "zstd"}
        )

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content.startswith(b"(\xb5/\xfd")
        decompressed = decompress(content)
        assert decompressed == b""

    async def test_async_identity(self):
        response = await self.async_client.get("/async/")
        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        assert response.content.decode() == basic_html

    async def test_async_gzip(self):
        response = await self.async_client.get(
            "/async/", headers={"accept-encoding": "gzip"}
        )
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip_decompress(response.content)
        assert decompressed.decode() == basic_html

    async def test_async_brotli(self):
        response = await self.async_client.get(
            "/async/", headers={"accept-encoding": "br"}
        )
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"\x1b]\x01\x00")
        decompressed = brotli_decompress(response.content)
        assert decompressed.decode() == basic_html

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    async def test_async_zstd(self):
        from compression.zstd import decompress

        response = await self.async_client.get(
            "/async/", headers={"accept-encoding": "zstd"}
        )
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"
        assert response.content.startswith(b"(\xb5/\xfd")
        decompressed = decompress(response.content)
        assert decompressed.decode() == basic_html

    async def test_async_streaming_identity(self):
        response = await self.async_client.get("/async/streaming/")
        assert isinstance(response, StreamingHttpResponse)
        assert response.status_code == HTTPStatus.OK
        assert "content-encoding" not in response.headers
        assert "vary" not in response.headers
        content = b""
        async for chunk in response.streaming_content:  # type: ignore[union-attr]
            content += chunk
        assert content.decode() == basic_html

    async def test_async_streaming_gzip(self):
        response = await self.async_client.get(
            "/async/streaming/", headers={"accept-encoding": "gzip"}
        )
        assert isinstance(response, StreamingHttpResponse)
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        content = b""
        async for chunk in response.streaming_content:  # type: ignore[union-attr]
            content += chunk
        assert content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip.decompress(content)
        assert decompressed.decode() == basic_html

    async def test_async_streaming_brotli(self):
        response = await self.async_client.get(
            "/async/streaming/", headers={"accept-encoding": "br"}
        )
        assert isinstance(response, StreamingHttpResponse)
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "br"
        assert response.headers["vary"] == "accept-encoding"
        content = b""
        async for chunk in response.streaming_content:  # type: ignore[union-attr]
            content += chunk
        assert content.startswith(b"\x1b]\x01\x00")
        decompressed = brotli_decompress(content)
        assert decompressed.decode() == basic_html

    @pytest.mark.skipif(sys.version_info < (3, 14), reason="Python 3.14+")
    async def test_async_streaming_zstd(self):
        from compression.zstd import decompress

        response = await self.async_client.get(
            "/async/streaming/", headers={"accept-encoding": "zstd"}
        )
        assert isinstance(response, StreamingHttpResponse)
        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "zstd"
        assert response.headers["vary"] == "accept-encoding"
        content = b""
        async for chunk in response.streaming_content:  # type: ignore[union-attr]
            content += chunk
        assert content.startswith(b"(\xb5/\xfd")
        decompressed = decompress(content)
        assert decompressed.decode() == basic_html

    def test_binary(self):
        response = self.client.get("/binary/", headers={"accept-encoding": "gzip"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        content = response.getvalue()
        assert content.startswith(b"\x1f\x8b\x08")
        decompressed = gzip.decompress(content)
        assert decompressed.startswith(b"\x89PNG\r\n\x1a\n")

    def test_etag(self):
        response = self.client.get("/etag/", headers={"accept-encoding": "gzip"})

        assert response.status_code == HTTPStatus.OK
        assert response.headers["content-encoding"] == "gzip"
        assert response.headers["vary"] == "accept-encoding"
        assert response.headers["etag"] == 'W/"12345"'
        assert response.content.startswith(b"\x1f\x8b\x08")


class UpstreamSourceTests(SimpleTestCase):
    @pytest.mark.skipif(django.VERSION < (6, 0), reason="Django 6.0+")
    def test_expected_upstream_source(self):
        # Fail when upstream source changes.
        source = inspect.getsource(django_middleware_gzip)
        expected = dedent("""\
        from django.utils.cache import patch_vary_headers
        from django.utils.deprecation import MiddlewareMixin
        from django.utils.regex_helper import _lazy_re_compile
        from django.utils.text import compress_sequence, compress_string

        re_accepts_gzip = _lazy_re_compile(r"\\bgzip\\b")


        class GZipMiddleware(MiddlewareMixin):
            \"\"\"
            Compress content if the browser allows gzip compression.
            Set the Vary header accordingly, so that caches will base their storage
            on the Accept-Encoding header.
            \"\"\"

            max_random_bytes = 100

            def process_response(self, request, response):
                # It's not worth attempting to compress really short responses.
                if not response.streaming and len(response.content) < 200:
                    return response

                # Avoid gzipping if we've already got a content-encoding.
                if response.has_header("Content-Encoding"):
                    return response

                patch_vary_headers(response, ("Accept-Encoding",))

                ae = request.META.get("HTTP_ACCEPT_ENCODING", "")
                if not re_accepts_gzip.search(ae):
                    return response

                if response.streaming:
                    if response.is_async:
                        # pull to lexical scope to capture fixed reference in case
                        # streaming_content is set again later.
                        original_iterator = response.streaming_content

                        async def gzip_wrapper():
                            async for chunk in original_iterator:
                                yield compress_string(
                                    chunk,
                                    max_random_bytes=self.max_random_bytes,
                                )

                        response.streaming_content = gzip_wrapper()
                    else:
                        response.streaming_content = compress_sequence(
                            response.streaming_content,
                            max_random_bytes=self.max_random_bytes,
                        )
                    # Delete the `Content-Length` header for streaming content, because
                    # we won't know the compressed size until we stream it.
                    del response.headers["Content-Length"]
                else:
                    # Return the compressed content only if it's actually shorter.
                    compressed_content = compress_string(
                        response.content,
                        max_random_bytes=self.max_random_bytes,
                    )
                    if len(compressed_content) >= len(response.content):
                        return response
                    response.content = compressed_content
                    response.headers["Content-Length"] = str(len(response.content))

                # If there is a strong ETag, make it weak to fulfill the requirements
                # of RFC 9110 Section 8.8.1 while also allowing conditional request
                # matches on ETags.
                etag = response.get("ETag")
                if etag and etag.startswith('"'):
                    response.headers["ETag"] = "W/" + etag
                response.headers["Content-Encoding"] = "gzip"

                return response
        """)
        assert source == expected


py314 = sys.version_info >= (3, 14)


class BestCodingTests(ParametrizedTestCase, SimpleTestCase):
    @parametrize(
        "given,expected",
        [
            # Huge
            ("gzip, " * 1000, "identity"),
            # Empty
            ("", "identity"),
            (",", "identity"),
            (",,,", "identity"),
            ("   ", "identity"),
            (", , ,", "identity"),
            (" , , ", "identity"),
            # Star
            ("*", "identity"),
            (" * ", "identity"),
            ("*;q=0", "identity"),
            ("*;q=0.0", "identity"),
            ("*;q=0.1", "identity"),
            ("*;q=0.5", "identity"),
            ("*;q=0.9", "identity"),
            ("*;q=1", "identity"),
            ("*;q=garbage", "identity"),
            ("*;q=,gzip", "identity"),
            # Supported
            ("gzip", "gzip"),
            ("br", "br"),
            ("gzip, br", "br"),
            ("br, gzip", "br"),
            ("zstd, gzip", "zstd" if py314 else "gzip"),
            ("gzip, zstd", "zstd" if py314 else "gzip"),
            ("br, zstd", "zstd" if py314 else "br"),
            ("zstd, br", "zstd" if py314 else "br"),
            ("gzip, br, zstd", "zstd" if py314 else "br"),
            ("zstd, br, gzip", "zstd" if py314 else "br"),
            ("br, gzip, zstd", "zstd" if py314 else "br"),
            ("zstd, gzip, br", "zstd" if py314 else "br"),
            # Quality values
            ("gzip;q=0", "identity"),
            ("gzip;q=whatever", "identity"),
            ("gzip;q=0.9", "gzip"),
            ("br;q=0.9", "br"),
            ("zstd;q=0.9", "zstd" if py314 else "identity"),
            ("gzip;q=0.5, br;q=0.9", "br"),
            ("br;q=0.5, gzip;q=0.9", "gzip"),
            ("zstd;q=0.5, gzip;q=0.9", "gzip"),
            ("gzip;q=0.5, zstd;q=0.9", "zstd" if py314 else "gzip"),
            ("br;q=0.5, zstd;q=0.9", "zstd" if py314 else "br"),
            ("zstd;q=0.5, br;q=0.9", "br" if py314 else "br"),
            ("zstd;q=0.5, br", "br"),
            ("gzip;q=0.9, br;q=0.5", "gzip"),
            ("br;q=0.9, gzip;q=0.5", "br"),
            ("zstd;q=0.9, gzip;q=0.5", "zstd" if py314 else "gzip"),
            ("gzip;q=0.9, zstd;q=0.5", "gzip"),
            ("br;q=0.9, zstd;q=0.5", "br"),
            ("zstd;q=0.9, br;q=0.5", "zstd" if py314 else "br"),
            ("gzip;q=0.8, br;q=0.9, zstd;q=0.7", "br"),
            ("br;q=0.8, gzip;q=0.9, zstd;q=0.7", "gzip"),
            ("zstd;q=0.8, gzip;q=0.9, br;q=0.7", "gzip"),
            ("gzip;q=0.8, zstd;q=0.9, br;q=0.7", "zstd" if py314 else "gzip"),
            ("br;q=0.8, zstd;q=0.9, gzip;q=0.7", "zstd" if py314 else "br"),
            ("zstd;q=0.8, br;q=0.9, gzip;q=0.7", "br"),
            # Unsupported
            ("supercompression", "identity"),
            ("supercompression, gzip", "gzip"),
            ("gzip, supercompression", "gzip"),
            ("supercompression;q=0.9, gzip;q=0.8", "gzip"),
            ("gzip;q=0.9, supercompression;q=0.8", "gzip"),
            ("zstd, gzip, supercompression", "zstd" if py314 else "gzip"),
            # Unknown parameters
            ("gzip;anything=1", "identity"),
            ("gzip;anything=1;other=2", "identity"),
            ("gzip; q=0.9; anything=1", "identity"),
            ("gzip; anything=1; q=0.9", "identity"),
        ],
    )
    def test_best_coding(self, given, expected):
        assert best_coding(given) == expected

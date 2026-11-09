from __future__ import annotations

import re
import sys
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Callable,
    Generator,
    Iterator,
)
from functools import lru_cache, partial
from gzip import GzipFile
from gzip import compress as gzip_compress
from http import HTTPStatus
from secrets import randbelow, token_urlsafe
from types import MappingProxyType
from typing import Literal, assert_never, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.utils.cache import patch_vary_headers
from django.utils.text import StreamingBuffer

# Try to import Zstandard
if sys.version_info >= (3, 14):
    # Try the built-in but optional compression.zstd first, then fall back to
    # backports.zstd if installed.
    try:
        from compression.zstd import ZstdCompressor
        from compression.zstd import compress as zstd_compress

        HAVE_ZSTD = True
    except ImportError:  # pragma: no cover
        try:
            from backports.zstd import ZstdCompressor  # type: ignore [no-redef]
            from backports.zstd import (  # type: ignore [no-redef]
                compress as zstd_compress,
            )

            HAVE_ZSTD = True
        except ImportError:
            HAVE_ZSTD = False
else:
    from backports.zstd import ZstdCompressor
    from backports.zstd import compress as zstd_compress

    HAVE_ZSTD = True

# Try to import Brotli
try:
    from brotli import Compressor as BrotliCompressor
    from brotli import compress as brotli_compress

    HAVE_BROTLI = True
except ImportError:  # pragma: no cover
    HAVE_BROTLI = False


class HttpCompressionMiddleware:
    """
    Compress content with the best-supported encoding that the client accepts.
    Set the Vary header accordingly, so that caches will base their storage
    on the Accept-Encoding header.
    """

    max_random_bytes = 99

    # Match Django’s GZipMiddleware, which uses level 6 (out of 1-9).
    gzip_compression_level = 6

    # Copy CloudFlare’s default quality setting (out of 0-11), to balance
    # speed versus savings.
    # https://blog.cloudflare.com/results-experimenting-brotli/
    brotli_compression_quality = 4

    # Copy CloudFlare again and use zstd’s default level, 3. zstd supports a
    # broad range of levels, including negative ones for faster compression.
    # https://blog.cloudflare.com/new-standards/#:~:text=level%20of%203
    zstandard_compression_level = 3

    # Seeded from Caddy’s default list of compressible content types
    # https://caddyserver.com/docs/caddyfile/directives/encode
    content_type_re = re.compile(
        r"""
        ^(?:
            application/(?:
                atom\+xml |
                eot |
                # Exclude already-compressed WOFF fonts under their legacy type,
                # which WhiteNoise still uses.
                font(?!-woff) |
                geo\+json |
                graphql\+json |
                javascript |
                json |
                ld\+json |
                manifest\+json |
                opentype |
                otf |
                rss\+xml |
                truetype |
                ttf |
                vnd\.api\+json |
                vnd\.ms-fontobject |
                wasm |
                x-httpd-cgi |
                x-javascript |
                x-opentype |
                x-otf |
                x-perl |
                x-protobuf |
                x-ttf |
                xhtml\+xml |
                xml
            ) |
            font/(?!woff).* |
            image/svg\+xml |
            image/vnd\.microsoft\.icon |
            image/x-icon |
            multipart/bag |
            multipart/mixed |
            text/.*
        )
    """,
        re.VERBOSE | re.IGNORECASE,
    )

    sync_capable = True
    async_capable = True

    def __init__(
        self,
        get_response: (
            Callable[[HttpRequest], HttpResponseBase]
            | Callable[[HttpRequest], Awaitable[HttpResponseBase]]
        ),
    ) -> None:
        self.get_response = get_response
        self.async_mode = iscoroutinefunction(self.get_response)

        if self.async_mode:
            # Mark the class as async-capable, but do the actual switch
            # inside __call__ to avoid swapping out dunder methods
            markcoroutinefunction(self)

    def __call__(
        self, request: HttpRequest
    ) -> HttpResponseBase | Awaitable[HttpResponseBase]:
        if self.async_mode:
            return self.__acall__(request)
        response = self.get_response(request)
        assert isinstance(response, HttpResponseBase)
        self.maybe_compress(request, response)
        return response

    async def __acall__(self, request: HttpRequest) -> HttpResponseBase:
        result = self.get_response(request)
        assert not isinstance(result, HttpResponseBase)  # type narrow
        response = await result
        self.maybe_compress(request, response)
        return response

    def maybe_compress(self, request: HttpRequest, response: HttpResponseBase) -> None:
        # Responses with these statuses can't have content, so compressing would
        # add a body:
        # https://www.rfc-editor.org/rfc/rfc9110#section-6.4.1-8
        if response.status_code < 200 or response.status_code in (
            HTTPStatus.NO_CONTENT,
            HTTPStatus.NOT_MODIFIED,
        ):
            # A 304 must have the Vary header that the 200 response would
            # have, so caches update their stored response consistently, as
            # Caddy does:
            # https://www.rfc-editor.org/rfc/rfc9110#section-15.4.5
            if response.status_code == HTTPStatus.NOT_MODIFIED:
                patch_vary_headers(response, ("accept-encoding",))
            return

        # Only compress known-compressible content types
        content_type = response.headers.get("content-type", "").split(";", 1)[0]
        if not self.content_type_re.match(content_type):
            return

        # It's not worth attempting to compress really short responses.
        if isinstance(response, HttpResponse) and len(response.content) < 50:
            return

        # Avoid gzipping if we've already got a content-encoding.
        if "content-encoding" in response.headers:
            return

        # Byte ranges refer to the encoded content, so compressing a partial
        # response would make its Content-Range incorrect, as Caddy notes:
        # https://www.rfc-editor.org/rfc/rfc9110#section-14.4
        if response.status_code == HTTPStatus.PARTIAL_CONTENT:
            return

        accept_encoding = request.headers.get("accept-encoding", "")
        coding = best_coding(accept_encoding)
        if coding == "identity":
            return

        patch_vary_headers(response, ("accept-encoding",))

        if response.streaming:
            response = cast(StreamingHttpResponse, response)
            if response.is_async:
                streaming_content = cast(
                    AsyncIterator[bytes], response.streaming_content
                )

                if coding == "gzip":
                    compressed_wrapper = partial(
                        gzip_compress_sequence_async,
                        streaming_content,
                        level=self.gzip_compression_level,
                    )

                elif coding == "br":
                    compressed_wrapper = partial(
                        brotli_compress_sequence_async,
                        streaming_content,
                        quality=self.brotli_compression_quality,
                    )
                elif coding == "zstd":
                    compressed_wrapper = partial(
                        zstd_compress_sequence_async,
                        streaming_content,
                        level=self.zstandard_compression_level,
                    )
                else:  # pragma: no cover
                    assert_never(coding)

                response.streaming_content = compressed_wrapper()
            else:
                if coding == "gzip":
                    response.streaming_content = gzip_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
                        level=self.gzip_compression_level,
                    )
                elif coding == "br":
                    response.streaming_content = brotli_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
                        quality=self.brotli_compression_quality,
                    )
                elif coding == "zstd":
                    response.streaming_content = zstd_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
                        level=self.zstandard_compression_level,
                    )
                else:  # pragma: no cover
                    assert_never(coding)
            # Delete the `Content-Length` header for streaming content, because
            # we won't know the compressed size until we stream it.
            del response.headers["content-length"]
        else:
            response = cast(HttpResponse, response)
            # Return the compressed content only if it's actually shorter.
            if coding == "gzip":
                compressed_content = gzip_compress(
                    response.content,
                    compresslevel=self.gzip_compression_level,
                    mtime=0,
                )
            elif coding == "br":
                compressed_content = brotli_compress(
                    response.content,
                    quality=self.brotli_compression_quality,
                )
            elif coding == "zstd":
                compressed_content = zstd_compress(
                    response.content,
                    level=self.zstandard_compression_level,
                )
            else:  # pragma: no cover
                assert_never(coding)

            if len(compressed_content) >= len(response.content):  # pragma: no cover
                return
            response.content = compressed_content
            response.headers["content-length"] = str(len(response.content))

        # BREACH mitigation: add a padding header of random length
        if self.max_random_bytes:
            response.headers["x-noise"] = token_urlsafe(
                randbelow(self.max_random_bytes + 1)
            )

        # If there is a strong ETag, make it weak to fulfill the requirements
        # of RFC 9110 Section 8.8.1 while also allowing conditional request
        # matches on ETags.
        etag = response.headers.get("etag")
        if etag and etag.startswith('"'):
            response.headers["etag"] = "W/" + etag

        # Byte ranges refer to the encoded content, which isn't stable, so
        # stop advertising range support, as Caddy does. Otherwise a client
        # could resume a compressed download with a range of uncompressed
        # bytes.
        # https://www.rfc-editor.org/rfc/rfc9110#section-14.3
        response.headers.pop("accept-ranges", None)

        response.headers["content-encoding"] = coding


codings = MappingProxyType(
    {
        **({"zstd": 0} if HAVE_ZSTD else {}),
        **({"br": 1} if HAVE_BROTLI else {}),
        "gzip": 2,
        "identity": 3,
    }
)

Coding = Literal["identity", "gzip", "br", "zstd"]

# Recipients should treat x-gzip as equivalent to gzip:
# https://www.rfc-editor.org/rfc/rfc9110#section-8.4.1.3
coding_aliases = MappingProxyType({"x-gzip": "gzip"})


def best_coding(accept_encoding: str) -> Coding:
    if len(accept_encoding) > 2048:
        # Protect against DoS attacks by limiting the length we’re willing to parse
        return "identity"

    # Content codings and parameter names are case-insensitive:
    # https://www.rfc-editor.org/rfc/rfc9110#section-8.4.1
    return _best_coding(accept_encoding.lower())


# Browsers send a limited set of Accept-Encoding headers, so cache parsed results
@lru_cache
def _best_coding(accept_encoding: str) -> Coding:
    options = []
    for part in accept_encoding.split(","):
        stripped = part.strip()
        if not stripped:
            continue
        parsed = _parse_part(stripped)
        if parsed is not None:
            options.append(parsed)

    options.sort(key=part_key)
    return options[0][2] if options else "identity"


def part_key(part: tuple[float, int, str]) -> tuple[float, int]:
    return -part[0], part[1]


def _parse_part(
    part: str,
) -> tuple[float, int, Coding] | None:
    part = coding_aliases.get(part, part)
    try:
        preference = codings[part]
    except KeyError:
        pass
    else:
        return (1.0, preference, cast(Coding, part))

    if part.startswith("*"):
        return None

    if ";" in part:
        coding, params = part.split(";", 1)
        coding = coding.strip()
        coding = coding_aliases.get(coding, coding)
        if coding in codings:
            params = params.strip()
            if params.startswith("q="):
                try:
                    q = float(params[2:])
                except ValueError:
                    pass
                else:
                    if 0 < q <= 1:
                        return (q, codings[coding], cast(Coding, coding))

    return None


def gzip_compress_sequence(
    sequence: Iterator[bytes], *, level: int
) -> Generator[bytes]:
    """
    Copy of Django’s compress_sequence() but with streaming response flushing
    bug fixed and random bytes feature removed in favour of x-noise header.
    """
    buf = StreamingBuffer()
    with GzipFile(
        filename=None, mode="wb", compresslevel=level, fileobj=buf, mtime=0
    ) as zfile:
        # Output headers...
        yield b""  # Optimization
        for item in sequence:
            zfile.write(item)
            zfile.flush()  # Bug fix
            data = buf.read()
            if data:
                yield data
    yield buf.read()


async def gzip_compress_sequence_async(
    sequence: AsyncIterator[bytes], *, level: int
) -> AsyncGenerator[bytes]:
    """
    Fixed version of Django's gzip_wrapper(), and with random bytes feature
    removed in favour of x-noise header.
    """
    buf = StreamingBuffer()
    with GzipFile(
        filename=None, mode="wb", compresslevel=level, fileobj=buf, mtime=0
    ) as zfile:
        # Output headers...
        yield b""  # Optimization
        async for item in sequence:
            zfile.write(item)
            zfile.flush()  # Bug fix
            data = buf.read()
            if data:
                yield data
    yield buf.read()


def brotli_compress_sequence(
    sequence: Iterator[bytes], *, quality: int
) -> Generator[bytes]:
    # Output headers
    yield b""

    compressor = BrotliCompressor(quality=quality)
    for item in sequence:
        data = compressor.process(item)
        data += compressor.flush()
        if data:  # pragma: no branch
            yield data
    out = compressor.finish()
    if out:  # pragma: no branch
        yield out


async def brotli_compress_sequence_async(
    sequence: AsyncIterator[bytes], *, quality: int
) -> AsyncGenerator[bytes]:
    # Output headers
    yield b""

    compressor = BrotliCompressor(quality=quality)
    async for item in sequence:
        data = compressor.process(item)
        data += compressor.flush()
        if data:  # pragma: no branch
            yield data
    out = compressor.finish()
    if out:  # pragma: no branch
        yield out


def zstd_compress_sequence(
    sequence: Iterator[bytes], *, level: int
) -> Generator[bytes]:
    # Output headers
    yield b""

    compressor = ZstdCompressor(level=level)
    for item in sequence:
        data = compressor.compress(item, mode=ZstdCompressor.FLUSH_BLOCK)
        if data:  # pragma: no branch
            yield data
    out = compressor.flush(mode=ZstdCompressor.FLUSH_FRAME)
    if out:  # pragma: no branch
        yield out


async def zstd_compress_sequence_async(
    sequence: AsyncIterator[bytes], *, level: int
) -> AsyncGenerator[bytes]:
    # Output headers
    yield b""

    compressor = ZstdCompressor(level=level)
    async for item in sequence:
        data = compressor.compress(item, mode=ZstdCompressor.FLUSH_BLOCK)
        if data:  # pragma: no branch
            yield data
    out = compressor.flush(mode=ZstdCompressor.FLUSH_FRAME)
    if out:  # pragma: no branch
        yield out

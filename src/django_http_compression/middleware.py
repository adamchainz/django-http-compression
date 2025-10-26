from __future__ import annotations

import re
from collections.abc import (
    AsyncGenerator,
    AsyncIterator,
    Awaitable,
    Generator,
    Iterator,
)
from functools import lru_cache, partial
from gzip import GzipFile
from types import MappingProxyType
from typing import Callable, Literal, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.utils.cache import patch_vary_headers
from django.utils.text import (  # type: ignore [attr-defined]
    StreamingBuffer,
    _get_random_filename,
)
from django.utils.text import compress_string as gzip_compress
from typing_extensions import assert_never

try:
    from compression.zstd import ZstdCompressor
    from compression.zstd import compress as zstd_compress

    HAVE_ZSTD = True
except ImportError:
    try:
        from backports.zstd import ZstdCompressor
        from backports.zstd import compress as zstd_compress

        HAVE_ZSTD = True
    except ImportError:  # pragma: no cover
        HAVE_ZSTD = False

try:
    from brotli import Compressor as BrotliCompressor
    from brotli import compress as brotli_compress

    HAVE_BROTLI = True
except ImportError:  # pragma: no cover
    HAVE_BROTLI = False


# Copy CloudFlare’s default quality setting, to balance
# speed versus savings.
# https://blog.cloudflare.com/results-experimenting-brotli/
BROTLI_QUALITY = 4


class HttpCompressionMiddleware:
    """
    Compress content with the best-supported encoding that the client accepts.
    Set the Vary header accordingly, so that caches will base their storage
    on the Accept-Encoding header.
    """

    gzip_max_random_bytes = 100

    # Seeded from Caddy’s default list of compressible content types
    # https://caddyserver.com/docs/caddyfile/directives/encode
    content_type_re = re.compile(
        r"""
        ^(?:
            application/(?:
                atom\+xml |
                eot |
                font |
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
            font/.* |
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

        view = request.resolver_match
        if view and getattr(view.func, "no_http_compression", False):
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
                        max_random_bytes=self.gzip_max_random_bytes,
                    )

                elif coding == "br":
                    compressed_wrapper = partial(
                        brotli_compress_sequence_async,
                        streaming_content,
                    )
                elif coding == "zstd":
                    compressed_wrapper = partial(
                        zstd_compress_sequence_async,
                        streaming_content,
                    )
                else:  # pragma: no cover
                    assert_never(coding)

                response.streaming_content = compressed_wrapper()
            else:
                if coding == "gzip":
                    response.streaming_content = gzip_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
                        max_random_bytes=self.gzip_max_random_bytes,
                    )
                elif coding == "br":
                    response.streaming_content = brotli_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
                    )
                elif coding == "zstd":
                    response.streaming_content = zstd_compress_sequence(
                        response.streaming_content,  # type: ignore [arg-type]
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
                    max_random_bytes=self.gzip_max_random_bytes,
                )
            elif coding == "br":
                compressed_content = brotli_compress(
                    response.content,
                    quality=BROTLI_QUALITY,
                )
            elif coding == "zstd":
                compressed_content = zstd_compress(
                    response.content,
                    # Copy CloudFlare again and use the default level, 3.
                    # https://blog.cloudflare.com/new-standards/#:~:text=level%20of%203
                )
            else:  # pragma: no cover
                assert_never(coding)

            if len(compressed_content) >= len(response.content):  # pragma: no cover
                return
            response.content = compressed_content
            response.headers["content-length"] = str(len(response.content))

        # If there is a strong ETag, make it weak to fulfill the requirements
        # of RFC 9110 Section 8.8.1 while also allowing conditional request
        # matches on ETags.
        etag = response.headers.get("etag")
        if etag and etag.startswith('"'):
            response.headers["etag"] = "W/" + etag

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


def best_coding(accept_encoding: str) -> Coding:
    if len(accept_encoding) > 2048:
        # Protect against DoS attacks by limiting the length we’re willing to parse
        return "identity"

    return _best_coding(accept_encoding)


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
    try:
        preference = codings[part]
    except KeyError:
        pass
    else:
        return (1.0, preference, cast(Coding, part))

    if part.startswith("*"):
        return (1.0, -1, "identity")

    if ";" in part:
        coding, params = part.split(";", 1)
        coding = coding.strip()
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
    sequence: Iterator[bytes], *, max_random_bytes: int
) -> Generator[bytes]:
    """
    Copy of Django’s compress_sequence() but with streaming response flushing
    bug fixed.
    """
    buf = StreamingBuffer()
    filename = _get_random_filename(max_random_bytes) if max_random_bytes else None
    with GzipFile(
        filename=filename, mode="wb", compresslevel=6, fileobj=buf, mtime=0
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
    sequence: AsyncIterator[bytes], *, max_random_bytes: int
) -> AsyncGenerator[bytes]:
    """
    Fixed version of Django's gzip_wrapper().
    """
    buf = StreamingBuffer()
    filename = _get_random_filename(max_random_bytes) if max_random_bytes else None
    with GzipFile(
        filename=filename, mode="wb", compresslevel=6, fileobj=buf, mtime=0
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


def brotli_compress_sequence(sequence: Iterator[bytes]) -> Generator[bytes]:
    # Output headers
    yield b""

    compressor = BrotliCompressor(quality=BROTLI_QUALITY)
    for item in sequence:
        data = compressor.process(item)
        data += compressor.flush()
        if data:  # pragma: no branch
            yield data
    out = compressor.finish()
    if out:  # pragma: no branch
        yield out


async def brotli_compress_sequence_async(
    sequence: AsyncIterator[bytes],
) -> AsyncGenerator[bytes]:
    # Output headers
    yield b""

    compressor = BrotliCompressor()
    async for item in sequence:
        data = compressor.process(item)
        data += compressor.flush()
        if data:  # pragma: no branch
            yield data
    out = compressor.finish()
    if out:  # pragma: no branch
        yield out


def zstd_compress_sequence(sequence: Iterator[bytes]) -> Generator[bytes]:
    # Output headers
    yield b""

    compressor = ZstdCompressor()
    for item in sequence:
        data = compressor.compress(item, mode=ZstdCompressor.FLUSH_BLOCK)
        if data:  # pragma: no branch
            yield data
    out = compressor.flush(mode=ZstdCompressor.FLUSH_FRAME)
    if out:  # pragma: no branch
        yield out


async def zstd_compress_sequence_async(
    sequence: AsyncIterator[bytes],
) -> AsyncGenerator[bytes]:
    # Output headers
    yield b""

    compressor = ZstdCompressor()
    async for item in sequence:
        data = compressor.compress(item, mode=ZstdCompressor.FLUSH_BLOCK)
        if data:  # pragma: no branch
            yield data
    out = compressor.flush(mode=ZstdCompressor.FLUSH_FRAME)
    if out:  # pragma: no branch
        yield out

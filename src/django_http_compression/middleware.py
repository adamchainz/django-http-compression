from __future__ import annotations

from collections.abc import AsyncGenerator, Awaitable, Generator, Iterator
from functools import lru_cache, partial
from types import MappingProxyType
from typing import Callable, Literal, cast

from asgiref.sync import iscoroutinefunction, markcoroutinefunction
from brotli import Compressor as BrotliCompressor
from brotli import compress as brotli_compress
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.http.response import HttpResponseBase
from django.utils.cache import patch_vary_headers
from django.utils.text import compress_sequence as gzip_compress_sequence
from django.utils.text import compress_string as gzip_compress
from typing_extensions import assert_never

try:
    from compression.zstd import ZstdCompressor
    from compression.zstd import compress as zstd_compress

    HAVE_ZSTD = True
except ImportError:
    HAVE_ZSTD = False


class HttpCompressionMiddleware:
    """
    Compress content with the best-supported encoding that the client accepts.
    Set the Vary header accordingly, so that caches will base their storage
    on the Accept-Encoding header.
    """

    gzip_max_random_bytes = 100

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
        # It's not worth attempting to compress really short responses.
        if isinstance(response, HttpResponse) and len(response.content) < 200:
            return

        # Avoid gzipping if we've already got a content-encoding.
        if "content-encoding" in response.headers:
            return

        accept_encoding = request.headers.get("accept-encoding", "")
        coding = best_coding(accept_encoding)
        if coding == "identity":
            return

        patch_vary_headers(response, ("accept-encoding",))

        if response.streaming:
            response = cast(StreamingHttpResponse, response)
            if response.is_async:
                # pull to lexical scope to capture fixed reference in case
                # streaming_content is set again later.
                original_iterator = response.streaming_content

                if coding == "gzip":

                    async def compressed_wrapper() -> AsyncGenerator[bytes]:
                        # Mypy cannot narrow that original_iterator is async
                        async for chunk in original_iterator:  # type: ignore [union-attr]
                            yield gzip_compress(
                                chunk,
                                max_random_bytes=self.gzip_max_random_bytes,
                            )

                elif coding == "br":
                    compressed_wrapper = partial(
                        brotli_compress_sequence_async,
                        original_iterator,  # type: ignore [arg-type]
                    )
                elif coding == "zstd":
                    compressed_wrapper = partial(
                        zstd_compress_sequence_async,
                        original_iterator,  # type: ignore [arg-type]
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
                    # Copy CloudFlare’s default quality setting, to balance
                    # speed versus savings.
                    # https://blog.cloudflare.com/results-experimenting-brotli/
                    quality=4,
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
        "br": 1,
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


def brotli_compress_sequence(sequence: Iterator[bytes]) -> Generator[bytes]:
    # Output headers
    yield b""

    compressor = BrotliCompressor()
    for item in sequence:
        data = compressor.process(item)
        if data:  # pragma: no branch
            yield data
    out = compressor.finish()
    if out:  # pragma: no branch
        yield out


async def brotli_compress_sequence_async(
    sequence: AsyncGenerator[bytes, None],
) -> AsyncGenerator[bytes, None]:
    # Output headers
    yield b""

    compressor = BrotliCompressor()
    async for item in sequence:
        data = compressor.process(item)
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
    sequence: AsyncGenerator[bytes, None],
) -> AsyncGenerator[bytes, None]:
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

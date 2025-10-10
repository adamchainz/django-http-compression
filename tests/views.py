from __future__ import annotations

from collections.abc import AsyncGenerator, Generator
from pathlib import Path

from django.http import FileResponse, HttpRequest, HttpResponse, StreamingHttpResponse

basic_html = """\
<!doctype html>
<html>
  <head>
    <title>My awesome site</title>
  </head>
  <body>
    <h1>Magical ponies are the best</h1>
    <p>Here is a list of my favorite ponies:</p>
    <ol>
      <li>Fluttershy</li>
      <li>Rarity</li>
      <li>Twilight Sparkle</li>
      <li>Princess Luna</li>
      <li>Rainbow Dash</li>
    </ol>
  </body>
</html>
"""


def index(request: HttpRequest) -> HttpResponse:
    return HttpResponse(basic_html)


def short(request: HttpRequest) -> HttpResponse:
    return HttpResponse("short")


def encoded(request: HttpRequest) -> HttpResponse:
    return HttpResponse(basic_html, headers={"Content-Encoding": "supercompression"})


async def async_(request: HttpRequest) -> HttpResponse:
    return HttpResponse(basic_html)


def streaming(request: HttpRequest) -> StreamingHttpResponse:
    return StreamingHttpResponse(line for line in basic_html.splitlines(keepends=True))


def streaming_empty(request: HttpRequest) -> StreamingHttpResponse:
    def empty() -> Generator[bytes]:
        if False:  # pragma: no cover
            yield b""  # type: ignore[unreachable]

    return StreamingHttpResponse(empty())


def streaming_blanks(request: HttpRequest) -> StreamingHttpResponse:
    def empty() -> Generator[bytes]:
        yield b""
        yield b""

    return StreamingHttpResponse(empty())


async def async_streaming(request: HttpRequest) -> StreamingHttpResponse:
    async def lines() -> AsyncGenerator[str]:
        for line in basic_html.splitlines(keepends=True):
            yield line

    return StreamingHttpResponse(lines())


async def async_streaming_empty(request: HttpRequest) -> StreamingHttpResponse:
    async def empty() -> AsyncGenerator[bytes]:
        if False:  # pragma: no cover
            yield b""  # type: ignore[unreachable]

    return StreamingHttpResponse(empty())


async def async_streaming_blanks(request: HttpRequest) -> StreamingHttpResponse:
    async def empty() -> AsyncGenerator[bytes]:
        yield b""
        yield b""

    return StreamingHttpResponse(empty())


def binary(request: HttpRequest) -> FileResponse:
    module_dir = Path(__file__).parent
    return FileResponse(
        (module_dir / "pony.png").open("rb"),
        content_type="image/png",
    )


def etag(request: HttpRequest) -> HttpResponse:
    return HttpResponse(basic_html, headers={"ETag": '"12345"'})

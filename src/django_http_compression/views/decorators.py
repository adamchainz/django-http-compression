from __future__ import annotations

from collections.abc import Callable
from functools import wraps
from typing import Any, TypeVar

from asgiref.sync import iscoroutinefunction
from django.http import HttpRequest

_C = TypeVar("_C", bound=Callable[..., Any])


def no_compression(view_func: _C) -> _C:
    """Mark a view function for skipping HTTP compression."""

    if iscoroutinefunction(view_func):

        async def _view_wrapper(request: HttpRequest, *args: Any, **kwargs: Any) -> Any:
            return await view_func(request, *args, **kwargs)

    else:

        def _view_wrapper(  # type: ignore[misc]
            request: HttpRequest, *args: Any, **kwargs: Any
        ) -> Any:
            return view_func(request, *args, **kwargs)

    _view_wrapper.no_http_compression = True  # type: ignore[attr-defined]

    return wraps(view_func)(_view_wrapper)  # type: ignore[return-value]

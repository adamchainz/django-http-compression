from __future__ import annotations

import builtins
import sys

if sys.version_info >= (3, 10):
    anext = builtins.anext
else:

    async def anext(aiter):
        return await aiter.__anext__()

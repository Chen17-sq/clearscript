"""Compatibility shim — the server implementation lives in ``clearscript.api``.

The original module grew to ~1500 lines with 46 endpoints in one closure;
it is now split into per-domain routers under ``clearscript/api/``. This
module remains so existing imports (``from clearscript.server import
create_app, serve``) and docs keep working.
"""

from __future__ import annotations

from clearscript.api import create_app, serve
from clearscript.api.slugs import (
    _looks_like_pleasantry,
    _slug_hint_from_input,
    _sse_format,
)

__all__ = [
    "_looks_like_pleasantry",
    "_slug_hint_from_input",
    "_sse_format",
    "create_app",
    "serve",
]

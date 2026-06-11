"""FastAPI application factory, split into per-domain routers.

The original ``clearscript.server`` module grew to ~1500 lines with all 46
endpoints inside one ``create_app`` closure. This package splits it:

- ``deps``             — AppState (lazy config, library factory, provider resolution)
- ``models``           — Pydantic request/response models
- ``slugs``            — slug derivation + SSE helpers
- ``routes_core``      — SPA shell, health, example, formats
- ``routes_providers`` — provider listing + API-key keyring management
- ``routes_run``       — run / run-stream / run-file / export / cost
- ``routes_projects``  — project history, rerun, compare, downloads
- ``routes_library``   — terms / speakers / patterns / negatives /
                         bootstrap / export / import / health / inbox

``clearscript.server`` remains as a thin compatibility shim re-exporting
``create_app`` and ``serve``.
"""

from __future__ import annotations

import threading
import time
import webbrowser

from fastapi import FastAPI

from clearscript import __version__
from clearscript.api import (
    routes_core,
    routes_library,
    routes_projects,
    routes_providers,
    routes_run,
)
from clearscript.api.deps import AppState


def create_app() -> FastAPI:
    app = FastAPI(title="clearscript", version=__version__)
    state = AppState()
    for build in (
        routes_core.build_router,
        routes_providers.build_router,
        routes_run.build_router,
        routes_projects.build_router,
        routes_library.build_router,
    ):
        app.include_router(build(state))
    return app


def serve(host: str = "127.0.0.1", port: int = 7681, open_browser: bool = True) -> None:
    """Run the local web server (blocking)."""
    import uvicorn

    app = create_app()

    if open_browser:

        def _open() -> None:
            time.sleep(0.8)
            webbrowser.open(f"http://{host}:{port}")

        threading.Thread(target=_open, daemon=True).start()

    uvicorn.run(app, host=host, port=port, log_level="info")


__all__ = ["AppState", "create_app", "serve"]

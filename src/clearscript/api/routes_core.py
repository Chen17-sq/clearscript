"""Core routes: SPA shell, health, example transcript, supported formats."""

from __future__ import annotations

from importlib import resources
from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import HTMLResponse

from clearscript import __version__
from clearscript.api.deps import AppState
from clearscript.ingest import supported_extensions


def build_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html = resources.files("clearscript.web").joinpath("index.html").read_text(encoding="utf-8")
        # Disable browser caching of the SPA so version bumps are immediately
        # visible after `clearscript serve` restarts.
        return HTMLResponse(
            html,
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
            },
        )

    @router.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @router.get("/api/supported-formats")
    def get_supported_formats() -> dict:
        return {"extensions": supported_extensions()}

    @router.get("/api/example")
    def get_example() -> dict:
        # The example ships as package data so wheel installs get it too —
        # the old repo-relative path only worked from a git checkout, which
        # made "Load example" silently empty for pipx/uv-tool users.
        try:
            bundled = resources.files("clearscript.web").joinpath("example_transcript.txt")
            if bundled.is_file():
                return {"transcript": bundled.read_text(encoding="utf-8")}
        except (FileNotFoundError, ModuleNotFoundError):
            pass
        examples_root = (
            Path(__file__).resolve().parent.parent.parent.parent / "examples" / "01-basic-cleanup"
        )
        input_path = examples_root / "input.txt"
        if input_path.is_file():
            return {"transcript": input_path.read_text(encoding="utf-8")}
        return {"transcript": ""}

    return router

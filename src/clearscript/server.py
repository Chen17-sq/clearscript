"""FastAPI server for the local web UI.

Single-page app served at ``/``; JSON API under ``/api/*``. The whole thing
binds to 127.0.0.1 by default — never exposes itself to the network unless
the user explicitly passes ``--host 0.0.0.0``.
"""

from __future__ import annotations

import contextlib
import tempfile
import threading
import time
import webbrowser
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

from clearscript import __version__
from clearscript.config import Config, ensure_dirs, load_config
from clearscript.core.pipeline import Pipeline
from clearscript.export import write_docx
from clearscript.ingest.txt import TxtAdapter
from clearscript.library import Library
from clearscript.providers import build_provider


def create_app() -> FastAPI:
    app = FastAPI(title="clearscript", version=__version__)
    cfg_holder: dict[str, Config] = {}

    def cfg() -> Config:
        if "config" not in cfg_holder:
            c = load_config()
            ensure_dirs(c)
            cfg_holder["config"] = c
        return cfg_holder["config"]

    @app.get("/", response_class=HTMLResponse)
    def index() -> HTMLResponse:
        html = resources.files("clearscript.web").joinpath("index.html").read_text(encoding="utf-8")
        return HTMLResponse(html)

    @app.get("/api/health")
    def health() -> dict:
        return {"status": "ok", "version": __version__}

    @app.get("/api/providers")
    def list_providers() -> dict:
        c = cfg()
        return {
            "default": c.default_provider,
            "providers": [
                {
                    "name": p.name,
                    "type": p.type,
                    "default_model": p.default_model,
                    "models": p.models,
                    "has_key": (p.resolve_api_key() is not None) or p.type == "ollama",
                    "key_env": p.api_key_env,
                }
                for p in c.providers.values()
            ],
        }

    class RunRequest(BaseModel):
        transcript: str
        provider: str | None = None
        model: str | None = None
        title: str | None = None
        briefing: str | None = None

    class RunResponse(BaseModel):
        edited_markdown: str
        change_log: list[dict]
        input_tokens: int
        output_tokens: int
        model: str
        provider: str

    @app.post("/api/run", response_model=RunResponse)
    def run_pipeline(req: RunRequest) -> RunResponse:
        if not req.transcript.strip():
            raise HTTPException(400, "Transcript is empty.")

        c = cfg()
        try:
            provider_cfg = c.get_provider(req.provider)
        except KeyError as exc:
            raise HTTPException(400, str(exc)) from exc

        chosen_model = req.model or provider_cfg.default_model
        if not chosen_model:
            raise HTTPException(
                400,
                f"No model specified and provider {provider_cfg.name!r} has no default. "
                "Pick one in the model dropdown.",
            )

        try:
            llm = build_provider(provider_cfg)
        except RuntimeError as exc:
            raise HTTPException(400, str(exc)) from exc

        adapter = TxtAdapter()
        transcript = adapter.parse_string(req.transcript)

        library = Library(c.library_path)
        try:
            pipeline = Pipeline(
                provider=llm,
                model=chosen_model,
                library=library,
                briefing_context=req.briefing or "",
            )
            try:
                result = pipeline.run_on_transcript(transcript)
            except Exception as exc:
                raise HTTPException(500, f"Pipeline error: {exc}") from exc
        finally:
            library.close()

        return RunResponse(
            edited_markdown=result.edited_markdown,
            change_log=result.change_log,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
            provider=result.provider,
        )

    class ExportRequest(BaseModel):
        markdown: str
        title: str | None = None

    @app.post("/api/export/docx")
    def export_docx(req: ExportRequest) -> Response:
        if not req.markdown.strip():
            raise HTTPException(400, "Nothing to export.")

        with tempfile.NamedTemporaryFile(suffix=".docx", delete=False) as tmp:
            out_path = Path(tmp.name)
        try:
            write_docx(req.markdown, out_path, title=req.title)
            data = out_path.read_bytes()
        finally:
            with contextlib.suppress(FileNotFoundError):
                out_path.unlink()

        return Response(
            content=data,
            media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            headers={"Content-Disposition": 'attachment; filename="clearscript-output.docx"'},
        )

    @app.get("/api/example")
    def get_example() -> dict:
        """Return the bundled example transcript for first-time users."""
        examples_root = Path(__file__).resolve().parent.parent.parent / "examples" / "01-basic-cleanup"
        input_path = examples_root / "input.txt"
        if input_path.is_file():
            return {"transcript": input_path.read_text(encoding="utf-8")}
        return {"transcript": ""}

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

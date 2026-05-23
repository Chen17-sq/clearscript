"""FastAPI server for the local web UI.

Single-page app served at ``/``; JSON API under ``/api/*``. The whole thing
binds to 127.0.0.1 by default — never exposes itself to the network unless
the user explicitly passes ``--host 0.0.0.0``.
"""

from __future__ import annotations

import contextlib
import json
import tempfile
import threading
import time
import webbrowser
from importlib import resources
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, Response, StreamingResponse
from pydantic import BaseModel, Field

from clearscript import __version__
from clearscript.config import Config, ensure_dirs, load_config
from clearscript.core.cost import actual_cost, estimate_cost
from clearscript.core.pipeline import Pipeline
from clearscript.export import write_docx
from clearscript.ingest import parse as parse_path
from clearscript.ingest import supported_extensions
from clearscript.ingest.json_ingest import JsonAdapter
from clearscript.ingest.md import MdAdapter
from clearscript.ingest.srt import SrtAdapter
from clearscript.ingest.txt import TxtAdapter
from clearscript.ingest.vtt import VttAdapter
from clearscript.library import Library, install_seed_pack
from clearscript.providers import build_provider
from clearscript.storage import ProjectStore

_FORMAT_ADAPTERS = {
    "txt": TxtAdapter,
    "md": MdAdapter,
    "srt": SrtAdapter,
    "vtt": VttAdapter,
    "json": JsonAdapter,
}


# Opening / mic-check phrases that should NOT become project slugs.
# Matched as a STARTSWITH check (not substring) so we catch "好的, 那咱们就
# 开始吧。我先简单介绍一下..." even though the line is long.
_PLEASANTRY_PATTERNS = (
    "测",  # 测一下麦 / 测试
    "听得见",
    "听不听得见",
    "能听见",
    "可以听到",
    "好的",  # 好的, 那咱们就开始吧
    "那咱们",  # 那咱们就开始吧
    "我先",  # 我先简单介绍一下
    "请",  # 请你简单介绍一下
    "没问题",
    "嗯",  # 嗯嗯
    "对",  # 对对对
    "hello",
    "hi ",
    "hi.",
    "hi!",
    "can you hear",
    "test",
    "okay",
    "ok ",
    "ok.",
    "ok,",
    "let me",
    "let's",
    "could you",
    "would you",
    "first of all",
)


def _sse_format(event_name: str, data: dict) -> str:
    """Encode a dict payload as a single Server-Sent Event."""
    return f"event: {event_name}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


def _looks_like_pleasantry(text: str) -> bool:
    """Return True if `text` looks like a transcript opener / mic check / chitchat.

    We're aggressive on purpose — over-rejecting lines just falls through to
    "transcript" as the slug fallback, which is better than ending up with
    "好的-那咱们就开始吧-我先简单介绍一下今天的主题".

    Rule: STARTSWITH any pleasantry pattern OR shorter than 6 chars.
    """
    lower = text.lower().strip()
    if len(lower) < 6:
        return True
    return any(lower.startswith(p) for p in _PLEASANTRY_PATTERNS)


def _slug_hint_from_input(
    text: str | None,
    filename: str | None,
    *,
    title: str | None = None,
    briefing: str | None = None,
) -> str:
    """Pick a project slug hint, preferring user-provided context over auto-extracted text.

    Priority order:
    1. Explicit title
    2. Filename stem
    3. First proper-noun-looking phrase from briefing
    4. First non-pleasantry speaker turn from the transcript
    5. Fallback "transcript"
    """
    if title and title.strip():
        return title.strip()[:50]
    if filename:
        stem = Path(filename).stem
        if stem and not _looks_like_pleasantry(stem):
            return stem
    if briefing and briefing.strip():
        # Take the first 50 chars of the briefing as a hint
        first_line = briefing.strip().splitlines()[0].strip()
        if first_line and not _looks_like_pleasantry(first_line):
            return first_line[:50]
    if text:
        for raw in text.splitlines():
            line = raw.strip()
            if not line:
                continue
            content = line
            for delim in (":", "："):
                if delim in line:
                    content = line.split(delim, 1)[1].strip()
                    break
            if not content:
                continue
            if _looks_like_pleasantry(content):
                continue
            return content[:50]
    return "transcript"


# ============ Request/response models (module-level so FastAPI can introspect) ============


class RunRequest(BaseModel):
    transcript: str
    format: str | None = None  # txt / md / srt / vtt / json — drives parser choice
    provider: str | None = None
    model: str | None = None
    title: str | None = None
    briefing: str | None = None


class RunResponse(BaseModel):
    edited_markdown: str
    change_log: list[dict]
    suggestions: list[dict]
    input_tokens: int
    output_tokens: int
    model: str
    provider: str
    num_chunks: int = 1  # > 1 when the transcript was auto-chunked
    project_slug: str | None = None  # set when the run was persisted to disk


class ExportRequest(BaseModel):
    markdown: str
    title: str | None = None


class TermPayload(BaseModel):
    canonical: str = ""
    type: str | None = Field(default=None)
    domain: str | None = None
    status: str | None = None
    definition: str | None = None
    notes: str | None = None
    aliases: list[str] = []


class SpeakerPayload(BaseModel):
    canonical_name: str = ""
    display_label: str = ""
    primary_language: str | None = None
    notes: str | None = None
    aliases: list[str] = []


class PatternPayload(BaseModel):
    title: str
    trigger_desc: str
    action: str
    rationale: str | None = None
    domain: str | None = None


class SuggestionItem(BaseModel):
    kind: str
    canonical: str | None = None
    canonical_name: str | None = None
    display_label: str | None = None
    type: str | None = None
    domain: str | None = None
    aliases_seen: list[str] = []
    title: str | None = None
    trigger_desc: str | None = None
    action: str | None = None
    rationale: str | None = None


class AcceptSuggestionsRequest(BaseModel):
    suggestions: list[SuggestionItem]


class EstimateCostRequest(BaseModel):
    transcript: str
    provider: str | None = None
    model: str | None = None


class UpdateTranscriptRequest(BaseModel):
    cleaned_markdown: str


class RerunRequest(BaseModel):
    provider: str | None = None
    model: str | None = None


class NegativePayload(BaseModel):
    """A negative-correction rule — 'do NOT change `text` to `do_not_change_to`'.

    Used by L3 to suppress over-eager substitutions. Common examples:
    keeping speaker colloquialisms ("蛮好的" not "很好"), preserving
    approximate phrasing ("差不多三四百人"), etc.
    """

    text: str
    do_not_change_to: str | None = None
    domain: str | None = None
    reason: str | None = None


# ============ App factory ============


def create_app() -> FastAPI:
    app = FastAPI(title="clearscript", version=__version__)
    cfg_holder: dict[str, Config] = {}

    def cfg() -> Config:
        if "config" not in cfg_holder:
            c = load_config()
            ensure_dirs(c)
            cfg_holder["config"] = c
        return cfg_holder["config"]

    seed_installed = {"done": False}

    def open_library() -> Library:
        lib = Library(cfg().library_path)
        # On first server boot, install the universal seed pack so the model
        # catches well-known ASR errors (DeFi → Dify, Tabby → Tavily, etc.)
        # without the user having to teach them.
        if not seed_installed["done"]:
            # Idempotent: add_term + add_negative skip rows that already
            # exist by canonical+scope, so calling on every boot is safe
            # even when the user already has data.
            with contextlib.suppress(Exception):
                install_seed_pack(lib, only_if_empty=False)
            seed_installed["done"] = True
        return lib

    @app.get("/", response_class=HTMLResponse)
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

    def _resolve_pipeline_pieces(
        provider_name: str | None, model_name: str | None
    ) -> tuple[object, str]:
        c = cfg()
        try:
            provider_cfg = c.get_provider(provider_name)
        except KeyError as exc:
            raise HTTPException(400, str(exc)) from exc

        chosen_model = model_name or provider_cfg.default_model
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
        return llm, chosen_model

    def _run_with_transcript(
        transcript_obj,
        llm,
        chosen_model: str,
        briefing: str,
        *,
        title: str | None = None,
        format_: str = "txt",
        save_input_text: str | None = None,
        save_input_bytes: bytes | None = None,
        save_input_filename: str | None = None,
    ) -> RunResponse:
        library = open_library()
        t0 = time.time()
        try:
            pipeline = Pipeline(
                provider=llm,
                model=chosen_model,
                library=library,
                briefing_context=briefing or "",
            )
            try:
                result = pipeline.run_on_transcript(transcript_obj)
            except Exception as exc:
                raise HTTPException(500, f"Pipeline error: {exc}") from exc
        finally:
            library.close()
        duration = time.time() - t0

        # Persist as a project so the user can browse it later.
        project_slug: str | None = None
        try:
            store = ProjectStore(cfg().projects_root)
            slug_hint = _slug_hint_from_input(
                save_input_text,
                save_input_filename,
                title=title,
                briefing=briefing,
            )
            project = store.create(slug_hint)
            project.save_run(
                title=title,
                format_=format_,
                provider=result.provider,
                model=result.model,
                input_text=save_input_text,
                input_bytes=save_input_bytes,
                input_filename=save_input_filename,
                briefing=briefing or "",
                edited_markdown=result.edited_markdown,
                change_log=result.change_log,
                suggestions=result.suggestions,
                input_tokens=result.input_tokens,
                output_tokens=result.output_tokens,
                duration_sec=duration,
            )
            project_slug = project.slug
        except OSError:
            # Persistence failure should not break the user's primary flow.
            project_slug = None

        return RunResponse(
            edited_markdown=result.edited_markdown,
            change_log=result.change_log,
            suggestions=result.suggestions,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            model=result.model,
            provider=result.provider,
            num_chunks=result.num_chunks,
            project_slug=project_slug,
        )

    @app.post("/api/run", response_model=RunResponse)
    def run_pipeline(req: RunRequest) -> RunResponse:
        if not req.transcript.strip():
            raise HTTPException(400, "Transcript is empty.")

        llm, chosen_model = _resolve_pipeline_pieces(req.provider, req.model)

        fmt = (req.format or "txt").lower()
        adapter_cls = _FORMAT_ADAPTERS.get(fmt, TxtAdapter)
        try:
            transcript_obj = adapter_cls().parse_string(req.transcript)
        except ValueError as exc:
            raise HTTPException(400, f"Failed to parse {fmt!r}: {exc}") from exc

        return _run_with_transcript(
            transcript_obj,
            llm,
            chosen_model,
            req.briefing or "",
            title=req.title,
            format_=fmt,
            save_input_text=req.transcript,
        )

    @app.post("/api/run-stream")
    def run_pipeline_stream(req: RunRequest, request: Request) -> StreamingResponse:
        """Server-Sent Events version of /api/run.

        Emits events: ``plan``, ``chunk_start``, ``chunk_done``, ``complete``,
        ``error``. Keeps the connection open while the pipeline runs so the
        UI can show real progress instead of a blind spinner.

        Same input contract as /api/run; same project persistence; same library
        side-effects. The only difference is the wire format.
        """
        if not req.transcript.strip():
            raise HTTPException(400, "Transcript is empty.")

        llm, chosen_model = _resolve_pipeline_pieces(req.provider, req.model)

        fmt = (req.format or "txt").lower()
        adapter_cls = _FORMAT_ADAPTERS.get(fmt, TxtAdapter)
        try:
            transcript_obj = adapter_cls().parse_string(req.transcript)
        except ValueError as exc:
            raise HTTPException(400, f"Failed to parse {fmt!r}: {exc}") from exc

        def event_stream():
            t0 = time.time()
            library = open_library()
            final_result = None
            try:
                pipeline = Pipeline(
                    provider=llm,
                    model=chosen_model,
                    library=library,
                    briefing_context=req.briefing or "",
                )
                for event in pipeline.iter_events(transcript_obj):
                    payload = {k: v for k, v in event.data.items() if k != "result"}
                    if event.name == "complete":
                        final_result = event.data.get("result")
                    yield _sse_format(event.name, payload)
            except Exception as exc:
                yield _sse_format("error", {"detail": f"pipeline error: {exc}"})
                return
            finally:
                library.close()

            # Persist the project (same logic as the sync path).
            project_slug = None
            cost_payload = None
            if final_result is not None:
                # Compute actual cost from real token counts so the UI can
                # show "$X.XX actual" instead of just the pre-run estimate.
                try:
                    p_cfg = cfg().get_provider(req.provider)
                    cost = actual_cost(
                        provider_type=p_cfg.type,
                        model=final_result.model,
                        input_tokens=final_result.input_tokens,
                        output_tokens=final_result.output_tokens,
                    )
                    cost_payload = cost.as_dict()
                except (KeyError, AttributeError):
                    cost_payload = None

                try:
                    duration = time.time() - t0
                    store = ProjectStore(cfg().projects_root)
                    slug_hint = _slug_hint_from_input(
                        req.transcript,
                        None,
                        title=req.title,
                        briefing=req.briefing,
                    )
                    project = store.create(slug_hint)
                    project.save_run(
                        title=req.title,
                        format_=fmt,
                        provider=final_result.provider,
                        model=final_result.model,
                        input_text=req.transcript,
                        briefing=req.briefing or "",
                        edited_markdown=final_result.edited_markdown,
                        change_log=final_result.change_log,
                        suggestions=final_result.suggestions,
                        input_tokens=final_result.input_tokens,
                        output_tokens=final_result.output_tokens,
                        duration_sec=duration,
                    )
                    # Augment meta with the actual cost so it shows up later
                    # in the Projects tab / CLI without recomputation.
                    if cost_payload:
                        meta = project.read_meta()
                        meta["actual_cost"] = cost_payload
                        project.write_meta(meta)
                    project_slug = project.slug
                except OSError:
                    project_slug = None

            yield _sse_format(
                "saved",
                {"project_slug": project_slug, "actual_cost": cost_payload},
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",  # disable nginx buffering if reverse-proxied
                "Connection": "keep-alive",
            },
        )

    @app.post("/api/projects/{slug}/rerun")
    def project_rerun(slug: str, req: RerunRequest, request: Request) -> StreamingResponse:
        """Re-run the editing pipeline on an existing project's raw input.

        The original input + briefing are loaded from disk, the pipeline
        runs again with the *current* library (so any newly-added terms
        take effect), and the output lands in a NEW project alongside the
        original — never overwriting. The new project's meta carries a
        ``rerun_of`` pointer back so the UI can show provenance.

        Emits the same SSE event stream as ``/api/run-stream`` so the UI
        can reuse its existing progress handler.
        """
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, "Project not found")
        orig_project = store.open(slug)
        orig_meta = orig_project.read_meta()

        input_pair = orig_project.read_input()
        if input_pair is None:
            raise HTTPException(
                422,
                "Cannot re-run: original input is binary or unreadable. "
                "Re-uploading via /api/run-file is required.",
            )
        input_text, fmt = input_pair
        briefing_text = orig_project.read_briefing()
        title = orig_meta.get("title")

        # Provider resolution priority:
        #   1. Explicit override in the request body
        #   2. The original project's provider (only if it's still in config)
        #   3. The config's default provider
        # The fallback in step 2 protects users who rename providers or
        # remove the one they used — the rerun stays runnable.
        configured = {p for p in cfg().providers}
        if req.provider:
            provider_choice = req.provider
        elif orig_meta.get("provider") in configured:
            provider_choice = orig_meta.get("provider")
        else:
            provider_choice = None  # let _resolve fall through to default

        model_choice = req.model or orig_meta.get("model")
        llm, chosen_model = _resolve_pipeline_pieces(provider_choice, model_choice)

        adapter_cls = _FORMAT_ADAPTERS.get(fmt, TxtAdapter)
        try:
            transcript_obj = adapter_cls().parse_string(input_text)
        except ValueError as exc:
            raise HTTPException(400, f"Failed to re-parse {fmt!r}: {exc}") from exc

        def event_stream():
            t0 = time.time()
            library = open_library()
            final_result = None
            try:
                pipeline = Pipeline(
                    provider=llm,
                    model=chosen_model,
                    library=library,
                    briefing_context=briefing_text,
                )
                for event in pipeline.iter_events(transcript_obj):
                    payload = {k: v for k, v in event.data.items() if k != "result"}
                    if event.name == "complete":
                        final_result = event.data.get("result")
                    yield _sse_format(event.name, payload)
            except Exception as exc:
                yield _sse_format("error", {"detail": f"pipeline error: {exc}"})
                return
            finally:
                library.close()

            new_slug: str | None = None
            cost_payload = None
            if final_result is not None:
                try:
                    p_cfg = cfg().get_provider(provider_choice)
                    cost = actual_cost(
                        provider_type=p_cfg.type,
                        model=final_result.model,
                        input_tokens=final_result.input_tokens,
                        output_tokens=final_result.output_tokens,
                    )
                    cost_payload = cost.as_dict()
                except (KeyError, AttributeError):
                    cost_payload = None

                try:
                    duration = time.time() - t0
                    new_project = store.create_rerun_of(slug)
                    new_project.save_run(
                        title=title,
                        format_=fmt,
                        provider=final_result.provider,
                        model=final_result.model,
                        input_text=input_text,
                        briefing=briefing_text,
                        edited_markdown=final_result.edited_markdown,
                        change_log=final_result.change_log,
                        suggestions=final_result.suggestions,
                        input_tokens=final_result.input_tokens,
                        output_tokens=final_result.output_tokens,
                        duration_sec=duration,
                    )
                    # Stamp the provenance back-link so the UI can show
                    # "rerun of <orig>" and link between siblings.
                    meta = new_project.read_meta()
                    meta["rerun_of"] = slug
                    if cost_payload:
                        meta["actual_cost"] = cost_payload
                    new_project.write_meta(meta)
                    new_slug = new_project.slug
                except OSError:
                    new_slug = None

            yield _sse_format(
                "saved",
                {
                    "project_slug": new_slug,
                    "rerun_of": slug,
                    "actual_cost": cost_payload,
                },
            )

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    @app.post("/api/run-file", response_model=RunResponse)
    async def run_pipeline_file(
        file: UploadFile = File(...),
        provider: str | None = Form(None),
        model: str | None = Form(None),
        title: str | None = Form(None),
        briefing: str | None = Form(None),
    ) -> RunResponse:
        """Run on an uploaded file (used for binary formats like .docx)."""
        if not file.filename:
            raise HTTPException(400, "Missing filename")

        suffix = Path(file.filename).suffix or ".bin"
        if suffix.lower() not in supported_extensions():
            raise HTTPException(
                400,
                f"Unsupported file type {suffix}. Supported: {', '.join(supported_extensions())}",
            )

        llm, chosen_model = _resolve_pipeline_pieces(provider, model)

        file_bytes = await file.read()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp_path = Path(tmp.name)
            tmp.write(file_bytes)

        try:
            try:
                transcript_obj = parse_path(tmp_path)
            except ValueError as exc:
                raise HTTPException(400, f"Failed to parse {suffix}: {exc}") from exc

            fmt = suffix.lstrip(".").lower()
            return _run_with_transcript(
                transcript_obj,
                llm,
                chosen_model,
                briefing or "",
                title=title,
                format_=fmt,
                save_input_bytes=file_bytes,
                save_input_filename=file.filename,
            )
        finally:
            with contextlib.suppress(FileNotFoundError):
                tmp_path.unlink()

    @app.get("/api/supported-formats")
    def get_supported_formats() -> dict:
        return {"extensions": supported_extensions()}

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

    @app.post("/api/estimate-cost")
    def estimate_cost_endpoint(req: EstimateCostRequest) -> dict:
        c = cfg()
        try:
            provider_cfg = c.get_provider(req.provider)
        except KeyError as exc:
            raise HTTPException(400, str(exc)) from exc
        chosen_model = req.model or provider_cfg.default_model or ""
        est = estimate_cost(
            transcript_text=req.transcript,
            provider_type=provider_cfg.type,
            model=chosen_model,
        )
        return {
            "provider": provider_cfg.name,
            "provider_type": provider_cfg.type,
            "model": chosen_model,
            **est.as_dict(),
        }

    @app.get("/api/example")
    def get_example() -> dict:
        examples_root = (
            Path(__file__).resolve().parent.parent.parent / "examples" / "01-basic-cleanup"
        )
        input_path = examples_root / "input.txt"
        if input_path.is_file():
            return {"transcript": input_path.read_text(encoding="utf-8")}
        return {"transcript": ""}

    # ============ Projects ============

    @app.get("/api/projects")
    def list_projects(limit: int = 200) -> dict:
        store = ProjectStore(cfg().projects_root)
        return {"projects": store.list_summaries(limit=limit)}

    @app.get("/api/projects/{slug}")
    def get_project(slug: str) -> dict:
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        return store.open(slug).detail()

    @app.delete("/api/projects/{slug}", status_code=204)
    def delete_project(slug: str) -> Response:
        store = ProjectStore(cfg().projects_root)
        if not store.delete(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        return Response(status_code=204)

    @app.patch("/api/projects/{slug}/transcript")
    def update_project_transcript(slug: str, payload: UpdateTranscriptRequest) -> dict:
        """Save user's hand-edits back to the project's cleaned markdown."""
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        project = store.open(slug)
        project.cleaned_md_path.write_text(payload.cleaned_markdown, encoding="utf-8")
        # Invalidate the cached docx so the next download regenerates from the
        # updated markdown rather than serving the stale version.
        if project.cleaned_docx_path.is_file():
            with contextlib.suppress(FileNotFoundError):
                project.cleaned_docx_path.unlink()
        return {"ok": True, "slug": slug, "bytes": len(payload.cleaned_markdown)}

    @app.get("/api/projects/{slug}/compare")
    def project_compare(slug: str, with_: str = Query(..., alias="with")) -> dict:
        """Return cleaned markdown for two projects + a unified diff.

        Used by the UI to show "what changed between this rerun and its
        parent" — and by users debugging library tweaks (run twice with
        a tweak in between, diff the result).

        Path slug is the *left* side (treated as 'old' in the diff),
        ``with`` is the *right* side ('new'). For a rerun project, call
        compare with slug=<original>&with=<rerun_slug> to see how the
        library tweak affected the output.
        """
        import difflib

        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        if not store.exists(with_):
            raise HTTPException(404, f"Project {with_!r} not found")

        left = store.open(slug).detail()
        right = store.open(with_).detail()

        left_md = left.get("cleaned_markdown") or ""
        right_md = right.get("cleaned_markdown") or ""

        diff_lines = list(
            difflib.unified_diff(
                left_md.splitlines(keepends=True),
                right_md.splitlines(keepends=True),
                fromfile=f"{slug}/transcript.md",
                tofile=f"{with_}/transcript.md",
                n=3,
            )
        )

        # Quick numeric summary so the UI can show "+N -M" without
        # re-parsing the diff client-side.
        added = sum(
            1 for line in diff_lines if line.startswith("+") and not line.startswith("+++")
        )
        removed = sum(
            1 for line in diff_lines if line.startswith("-") and not line.startswith("---")
        )

        return {
            "left": {
                "slug": slug,
                "title": left.get("title"),
                "cleaned_markdown": left_md,
                "model": left.get("model"),
                "created_at": left.get("created_at"),
            },
            "right": {
                "slug": with_,
                "title": right.get("title"),
                "cleaned_markdown": right_md,
                "model": right.get("model"),
                "created_at": right.get("created_at"),
            },
            "unified_diff": "".join(diff_lines),
            "stats": {
                "added": added,
                "removed": removed,
                "identical": left_md == right_md,
            },
        }

    @app.get("/api/projects/{slug}/transcript.md")
    def project_transcript_md(slug: str) -> Response:
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, "not found")
        path = store.open(slug).cleaned_md_path
        if not path.is_file():
            raise HTTPException(404, "no cleaned transcript")
        return Response(
            content=path.read_bytes(),
            media_type="text/markdown",
            headers={"Content-Disposition": f'attachment; filename="{slug}.md"'},
        )

    @app.get("/api/projects/{slug}/transcript.docx")
    def project_transcript_docx(slug: str) -> Response:
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, "not found")
        project = store.open(slug)
        # Generate on demand from the saved markdown — keeps storage lean.
        if not project.cleaned_docx_path.is_file():
            if not project.cleaned_md_path.is_file():
                raise HTTPException(404, "no cleaned transcript")
            md = project.cleaned_md_path.read_text(encoding="utf-8")
            write_docx(md, project.cleaned_docx_path)
        return Response(
            content=project.cleaned_docx_path.read_bytes(),
            media_type=("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
            headers={"Content-Disposition": f'attachment; filename="{slug}.docx"'},
        )

    @app.get("/api/projects/{slug}/input")
    def project_raw_input(slug: str) -> Response:
        store = ProjectStore(cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, "not found")
        project = store.open(slug)
        for path in project.raw_dir.glob("input.*"):
            return Response(
                content=path.read_bytes(),
                media_type="application/octet-stream",
                headers={
                    "Content-Disposition": f'attachment; filename="{path.name}"',
                },
            )
        raise HTTPException(404, "no input file stored")

    # ============ Library: stats ============

    @app.get("/api/library/stats")
    def library_stats() -> dict:
        lib = open_library()
        try:
            return lib.stats()
        finally:
            lib.close()

    # ============ Library: terms ============

    @app.get("/api/library/terms")
    def list_terms_endpoint(
        type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> dict:
        lib = open_library()
        try:
            return {
                "terms": lib.list_terms(
                    type_=type, domain=domain, status=status, search=search, limit=limit
                )
            }
        finally:
            lib.close()

    @app.post("/api/library/terms", status_code=201)
    def add_term_endpoint(payload: TermPayload) -> dict:
        if not payload.canonical.strip():
            raise HTTPException(400, "canonical is required")
        lib = open_library()
        try:
            term_id = lib.add_term(
                canonical=payload.canonical,
                type_=payload.type,
                domain=payload.domain,
                aliases=payload.aliases,
                definition=payload.definition,
            )
            if payload.status:
                lib.update_term(term_id, status=payload.status)
            return {"id": term_id}
        finally:
            lib.close()

    @app.patch("/api/library/terms/{term_id}")
    def update_term_endpoint(term_id: int, payload: TermPayload) -> dict:
        lib = open_library()
        try:
            lib.update_term(
                term_id,
                canonical=payload.canonical or None,
                type_=payload.type,
                domain=payload.domain,
                status=payload.status,
                definition=payload.definition,
                notes=payload.notes,
                aliases=payload.aliases if payload.aliases else None,
            )
            return {"ok": True}
        finally:
            lib.close()

    @app.delete("/api/library/terms/{term_id}", status_code=204)
    def delete_term_endpoint(term_id: int) -> Response:
        lib = open_library()
        try:
            lib.delete_term(term_id)
            return Response(status_code=204)
        finally:
            lib.close()

    @app.post("/api/library/terms/bulk-delete")
    def bulk_delete_terms_endpoint(payload: dict) -> dict:
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise HTTPException(400, "Body must be {ids: [int, ...]}")
        lib = open_library()
        try:
            deleted = lib.bulk_delete_terms(ids)
            return {"deleted": deleted}
        finally:
            lib.close()

    # ============ Library: export / import ============

    @app.get("/api/library/export")
    def library_export() -> Response:
        """Download the entire library as a JSON file the user can back up,
        share with a teammate, or commit to a private repo."""
        lib = open_library()
        try:
            payload = lib.export_dict()
        finally:
            lib.close()
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        return Response(
            content=body,
            media_type="application/json",
            headers={
                "Content-Disposition": 'attachment; filename="clearscript-library.json"',
            },
        )

    @app.get("/api/library/export.md")
    def library_export_markdown() -> Response:
        """Markdown view of the library — git-friendly, human-readable."""
        lib = open_library()
        try:
            md = lib.export_markdown()
        finally:
            lib.close()
        return Response(
            content=md,
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": 'attachment; filename="clearscript-library.md"',
            },
        )

    @app.get("/api/library/health")
    def library_health(stale_days: int = 90) -> dict:
        """Surface duplicates / low-confidence / stale terms for cleanup."""
        lib = open_library()
        try:
            return lib.health_check(stale_days=stale_days)
        finally:
            lib.close()

    @app.post("/api/library/import")
    def library_import(payload: dict) -> dict:
        """Merge an exported library back in. Caller passes the parsed JSON.

        Returns the merge summary (terms_added, terms_merged, etc.).
        """
        lib = open_library()
        try:
            try:
                summary = lib.import_dict(payload)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"summary": summary}
        finally:
            lib.close()

    # ============ Library: speakers ============

    @app.get("/api/library/speakers")
    def list_speakers_endpoint(search: str | None = None, limit: int = 500) -> dict:
        lib = open_library()
        try:
            return {"speakers": lib.list_speakers(search=search, limit=limit)}
        finally:
            lib.close()

    @app.post("/api/library/speakers", status_code=201)
    def add_speaker_endpoint(payload: SpeakerPayload) -> dict:
        if not payload.canonical_name.strip() or not payload.display_label.strip():
            raise HTTPException(400, "canonical_name and display_label are required")
        lib = open_library()
        try:
            sid = lib.add_speaker(
                canonical_name=payload.canonical_name,
                display_label=payload.display_label,
                aliases=payload.aliases,
                primary_language=payload.primary_language,
            )
            return {"id": sid}
        finally:
            lib.close()

    @app.patch("/api/library/speakers/{speaker_id}")
    def update_speaker_endpoint(speaker_id: int, payload: SpeakerPayload) -> dict:
        lib = open_library()
        try:
            lib.update_speaker(
                speaker_id,
                canonical_name=payload.canonical_name or None,
                display_label=payload.display_label or None,
                primary_language=payload.primary_language,
                notes=payload.notes,
                aliases=payload.aliases if payload.aliases else None,
            )
            return {"ok": True}
        finally:
            lib.close()

    @app.delete("/api/library/speakers/{speaker_id}", status_code=204)
    def delete_speaker_endpoint(speaker_id: int) -> Response:
        lib = open_library()
        try:
            lib.delete_speaker(speaker_id)
            return Response(status_code=204)
        finally:
            lib.close()

    # ============ Library: edit patterns ============

    @app.get("/api/library/patterns")
    def list_patterns_endpoint(domain: str | None = None) -> dict:
        lib = open_library()
        try:
            return {"patterns": lib.list_edit_patterns(domain=domain)}
        finally:
            lib.close()

    @app.post("/api/library/patterns", status_code=201)
    def add_pattern_endpoint(payload: PatternPayload) -> dict:
        lib = open_library()
        try:
            pid = lib.add_edit_pattern(
                title=payload.title,
                trigger_desc=payload.trigger_desc,
                action=payload.action,
                rationale=payload.rationale,
                domain=payload.domain,
            )
            return {"id": pid}
        finally:
            lib.close()

    @app.delete("/api/library/patterns/{pattern_id}", status_code=204)
    def delete_pattern_endpoint(pattern_id: int) -> Response:
        lib = open_library()
        try:
            lib.delete_edit_pattern(pattern_id)
            return Response(status_code=204)
        finally:
            lib.close()

    # ============ Library: bulk accept Mode B suggestions ============

    # ============ Library: negatives ============

    @app.get("/api/library/negatives")
    def list_negatives_endpoint() -> dict:
        lib = open_library()
        try:
            return {"negatives": lib.list_negatives()}
        finally:
            lib.close()

    @app.post("/api/library/negatives", status_code=201)
    def add_negative_endpoint(payload: NegativePayload) -> dict:
        if not payload.text.strip():
            raise HTTPException(400, "text is required")
        lib = open_library()
        try:
            lib.add_negative(
                text=payload.text,
                do_not_change_to=payload.do_not_change_to,
                domain=payload.domain,
                reason=payload.reason,
            )
            return {"ok": True}
        finally:
            lib.close()

    @app.delete("/api/library/negatives/{negative_id}", status_code=204)
    def delete_negative_endpoint(negative_id: int) -> Response:
        lib = open_library()
        try:
            deleted = lib.delete_negative(negative_id)
            if not deleted:
                raise HTTPException(404, f"Negative rule {negative_id} not found")
            return Response(status_code=204)
        finally:
            lib.close()

    @app.post("/api/library/accept-suggestions")
    def accept_suggestions(req: AcceptSuggestionsRequest) -> dict:
        lib = open_library()
        accepted = {"terms": 0, "speakers": 0, "patterns": 0, "skipped": 0}
        try:
            for s in req.suggestions:
                kind = s.kind.lower()
                if kind == "term" and s.canonical:
                    lib.add_term(
                        canonical=s.canonical,
                        type_=s.type,
                        domain=s.domain,
                        aliases=s.aliases_seen or [],
                    )
                    accepted["terms"] += 1
                elif kind == "speaker" and s.canonical_name and s.display_label:
                    lib.add_speaker(
                        canonical_name=s.canonical_name,
                        display_label=s.display_label,
                        aliases=s.aliases_seen or [],
                    )
                    accepted["speakers"] += 1
                elif kind == "edit_pattern" and s.title and s.trigger_desc and s.action:
                    lib.add_edit_pattern(
                        title=s.title,
                        trigger_desc=s.trigger_desc,
                        action=s.action,
                        rationale=s.rationale,
                        domain=s.domain,
                    )
                    accepted["patterns"] += 1
                else:
                    accepted["skipped"] += 1
            return {"accepted": accepted}
        finally:
            lib.close()

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

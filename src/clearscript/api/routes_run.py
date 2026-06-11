"""Run endpoints: sync run, SSE streaming run, file upload, export, cost."""

from __future__ import annotations

import contextlib
import tempfile
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import Response, StreamingResponse

from clearscript.api.deps import FORMAT_ADAPTERS, AppState
from clearscript.api.models import (
    EstimateCostRequest,
    ExportRequest,
    RunRequest,
    RunResponse,
)
from clearscript.api.slugs import _slug_hint_from_input, _sse_format
from clearscript.core.cost import actual_cost, estimate_cost
from clearscript.core.pipeline import Pipeline
from clearscript.export import write_docx
from clearscript.ingest import parse as parse_path
from clearscript.ingest import supported_extensions
from clearscript.ingest.txt import TxtAdapter
from clearscript.storage import ProjectStore


def build_router(state: AppState) -> APIRouter:
    router = APIRouter()

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
        library = state.open_library()
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
            store = ProjectStore(state.cfg().projects_root)
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

    @router.post("/api/run", response_model=RunResponse)
    def run_pipeline(req: RunRequest) -> RunResponse:
        if not req.transcript.strip():
            raise HTTPException(400, "Transcript is empty.")

        llm, chosen_model = state.resolve_pipeline_pieces(req.provider, req.model)

        fmt = (req.format or "txt").lower()
        adapter_cls = FORMAT_ADAPTERS.get(fmt, TxtAdapter)
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

    @router.post("/api/run-stream")
    def run_pipeline_stream(req: RunRequest, request: Request) -> StreamingResponse:
        """Server-Sent Events version of /api/run.

        Emits events: ``plan``, ``chunk_start``, ``chunk_delta``,
        ``chunk_done``, ``self_review_start/done/error``, ``complete``,
        ``saved``, ``error``. Keeps the connection open while the pipeline
        runs so the UI can show real progress instead of a blind spinner.

        Same input contract as /api/run; same project persistence; same
        library side-effects. The only difference is the wire format.
        """
        if not req.transcript.strip():
            raise HTTPException(400, "Transcript is empty.")

        llm, chosen_model = state.resolve_pipeline_pieces(req.provider, req.model)

        fmt = (req.format or "txt").lower()
        adapter_cls = FORMAT_ADAPTERS.get(fmt, TxtAdapter)
        try:
            transcript_obj = adapter_cls().parse_string(req.transcript)
        except ValueError as exc:
            raise HTTPException(400, f"Failed to parse {fmt!r}: {exc}") from exc

        def persist(final_result, t0: float) -> dict:
            """Save the finished run as a project. Never raises — a
            persistence failure must not kill the stream or lose the
            in-memory result the client already received."""
            project_slug = None
            cost_payload = None
            # Compute actual cost from real token counts so the UI can
            # show "$X.XX actual" instead of just the pre-run estimate.
            try:
                p_cfg = state.cfg().get_provider(req.provider)
                cost = actual_cost(
                    provider_type=p_cfg.type,
                    model=final_result.model,
                    input_tokens=final_result.input_tokens,
                    output_tokens=final_result.output_tokens,
                )
                cost_payload = cost.as_dict()
            except Exception:
                cost_payload = None

            try:
                duration = time.time() - t0
                store = ProjectStore(state.cfg().projects_root)
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
            except Exception:
                project_slug = None
            return {"project_slug": project_slug, "actual_cost": cost_payload}

        def event_stream():
            t0 = time.time()
            library = state.open_library()
            saved_payload: dict | None = None
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
                        # Persist BEFORE yielding 'complete': if the client
                        # disconnects, GeneratorExit lands at the next yield
                        # — the finished run must already be on disk by then.
                        final_result = event.data.get("result")
                        if final_result is not None:
                            saved_payload = persist(final_result, t0)
                    yield _sse_format(event.name, payload)
            except Exception as exc:
                yield _sse_format("error", {"detail": f"pipeline error: {exc}"})
                return
            finally:
                library.close()

            yield _sse_format(
                "saved",
                saved_payload or {"project_slug": None, "actual_cost": None},
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

    @router.post("/api/run-file", response_model=RunResponse)
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

        llm, chosen_model = state.resolve_pipeline_pieces(provider, model)

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

    @router.post("/api/export/docx")
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

    @router.post("/api/estimate-cost")
    def estimate_cost_endpoint(req: EstimateCostRequest) -> dict:
        c = state.cfg()
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

    return router

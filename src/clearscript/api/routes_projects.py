"""Project history endpoints: list, detail, delete, edit, compare, rerun, downloads."""

from __future__ import annotations

import contextlib
import difflib
import time

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from clearscript.api.deps import FORMAT_ADAPTERS, AppState
from clearscript.api.models import RerunRequest, UpdateTranscriptRequest
from clearscript.api.slugs import _sse_format
from clearscript.core.cost import actual_cost
from clearscript.core.pipeline import Pipeline
from clearscript.export import write_docx
from clearscript.ingest.txt import TxtAdapter
from clearscript.storage import ProjectStore


def build_router(state: AppState) -> APIRouter:
    router = APIRouter()

    @router.get("/api/projects")
    def list_projects(limit: int = 200) -> dict:
        store = ProjectStore(state.cfg().projects_root)
        return {"projects": store.list_summaries(limit=limit)}

    @router.get("/api/projects/{slug}")
    def get_project(slug: str) -> dict:
        store = ProjectStore(state.cfg().projects_root)
        if not store.exists(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        return store.open(slug).detail()

    @router.delete("/api/projects/{slug}", status_code=204)
    def delete_project(slug: str) -> Response:
        store = ProjectStore(state.cfg().projects_root)
        if not store.delete(slug):
            raise HTTPException(404, f"Project {slug!r} not found")
        return Response(status_code=204)

    @router.patch("/api/projects/{slug}/transcript")
    def update_project_transcript(slug: str, payload: UpdateTranscriptRequest) -> dict:
        """Save user's hand-edits back to the project's cleaned markdown."""
        store = ProjectStore(state.cfg().projects_root)
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

    @router.get("/api/projects/{slug}/compare")
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
        store = ProjectStore(state.cfg().projects_root)
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

    @router.post("/api/projects/{slug}/rerun")
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
        store = ProjectStore(state.cfg().projects_root)
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
        configured = set(state.cfg().providers)
        if req.provider:
            provider_choice = req.provider
        elif orig_meta.get("provider") in configured:
            provider_choice = orig_meta.get("provider")
        else:
            provider_choice = None  # let resolve fall through to default

        model_choice = req.model or orig_meta.get("model")
        llm, chosen_model = state.resolve_pipeline_pieces(provider_choice, model_choice)

        adapter_cls = FORMAT_ADAPTERS.get(fmt, TxtAdapter)
        try:
            transcript_obj = adapter_cls().parse_string(input_text)
        except ValueError as exc:
            raise HTTPException(400, f"Failed to re-parse {fmt!r}: {exc}") from exc

        def persist(final_result, t0: float) -> dict:
            """Save the rerun as a sibling project. Never raises."""
            new_slug: str | None = None
            cost_payload = None
            try:
                p_cfg = state.cfg().get_provider(provider_choice)
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
            except Exception:
                new_slug = None
            return {
                "project_slug": new_slug,
                "rerun_of": slug,
                "actual_cost": cost_payload,
            }

        def event_stream():
            t0 = time.time()
            library = state.open_library()
            saved_payload: dict | None = None
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
                        # Persist before yielding so a client disconnect at
                        # this point can't lose the finished rerun.
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
                saved_payload
                or {"project_slug": None, "rerun_of": slug, "actual_cost": None},
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

    @router.get("/api/projects/{slug}/transcript.md")
    def project_transcript_md(slug: str) -> Response:
        store = ProjectStore(state.cfg().projects_root)
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

    @router.get("/api/projects/{slug}/transcript.docx")
    def project_transcript_docx(slug: str) -> Response:
        store = ProjectStore(state.cfg().projects_root)
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

    @router.get("/api/projects/{slug}/input")
    def project_raw_input(slug: str) -> Response:
        store = ProjectStore(state.cfg().projects_root)
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

    return router

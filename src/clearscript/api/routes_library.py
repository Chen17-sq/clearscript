"""Library endpoints: stats, terms, speakers, patterns, negatives,
bootstrap, export/import, health, suggestions inbox, accept-suggestions."""

from __future__ import annotations

import json
import os
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response, StreamingResponse

from clearscript.api.deps import AppState
from clearscript.api.models import (
    AcceptSuggestionsRequest,
    BootstrapRequest,
    NegativePayload,
    PatternPayload,
    SpeakerPayload,
    TermPayload,
)
from clearscript.api.slugs import _sse_format
from clearscript.ingest.txt import TxtAdapter
from clearscript.library import Library
from clearscript.storage import ProjectStore


def build_router(state: AppState) -> APIRouter:
    router = APIRouter()

    # ============ Stats ============

    @router.get("/api/library/stats")
    def library_stats() -> dict:
        lib = state.open_library()
        try:
            return lib.stats()
        finally:
            lib.close()

    # ============ Terms ============

    @router.get("/api/library/terms")
    def list_terms_endpoint(
        type: str | None = None,
        domain: str | None = None,
        status: str | None = None,
        search: str | None = None,
        limit: int = 500,
    ) -> dict:
        lib = state.open_library()
        try:
            return {
                "terms": lib.list_terms(
                    type_=type, domain=domain, status=status, search=search, limit=limit
                )
            }
        finally:
            lib.close()

    @router.post("/api/library/terms", status_code=201)
    def add_term_endpoint(payload: TermPayload) -> dict:
        if not payload.canonical.strip():
            raise HTTPException(400, "canonical is required")
        lib = state.open_library()
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

    @router.patch("/api/library/terms/{term_id}")
    def update_term_endpoint(term_id: int, payload: TermPayload) -> dict:
        lib = state.open_library()
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

    @router.delete("/api/library/terms/{term_id}", status_code=204)
    def delete_term_endpoint(term_id: int) -> Response:
        lib = state.open_library()
        try:
            lib.delete_term(term_id)
            return Response(status_code=204)
        finally:
            lib.close()

    @router.post("/api/library/terms/bulk-delete")
    def bulk_delete_terms_endpoint(payload: dict) -> dict:
        ids = payload.get("ids") or []
        if not isinstance(ids, list) or not all(isinstance(i, int) for i in ids):
            raise HTTPException(400, "Body must be {ids: [int, ...]}")
        lib = state.open_library()
        try:
            deleted = lib.bulk_delete_terms(ids)
            return {"deleted": deleted}
        finally:
            lib.close()

    # ============ Bootstrap (batch entity extraction) ============

    @router.post("/api/library/bootstrap")
    def library_bootstrap(req: BootstrapRequest) -> StreamingResponse:
        """Run a lightweight entity-extraction pass over many raw
        transcripts and stream aggregated candidates back.

        Closes the cold-start gap: instead of cleaning transcripts one
        at a time and slowly compounding the library, the user dumps a
        stack of past transcripts here, accepts the merged candidates
        in one click, and starts cleaning with a warm library.

        Cheaper than ``/api/run`` — pure extraction, no rewriting, no
        chunking. Each transcript is one round-trip to the model.
        """
        from clearscript.core.bootstrap import bootstrap_from_transcripts

        texts = [t for t in (req.transcripts or []) if t and t.strip()]
        if not texts:
            raise HTTPException(400, "transcripts list is empty")
        if len(texts) > 50:
            raise HTTPException(
                400,
                f"too many transcripts ({len(texts)}); cap is 50 per bootstrap "
                "batch. Run multiple bootstrap rounds if you have more.",
            )

        llm, chosen_model = state.resolve_pipeline_pieces(req.provider, req.model)

        parsed: list = []
        for raw in texts:
            try:
                parsed.append(TxtAdapter().parse_string(raw))
            except ValueError as exc:
                raise HTTPException(400, f"Failed to parse transcript: {exc}") from exc

        def event_stream():
            try:
                for event in bootstrap_from_transcripts(
                    provider=llm,
                    model=chosen_model,
                    transcripts=parsed,
                ):
                    yield _sse_format(event.name, event.data)
            except Exception as exc:
                yield _sse_format("error", {"detail": f"bootstrap error: {exc}"})

        return StreamingResponse(
            event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ============ Export / Import ============

    @router.get("/api/library/export")
    def library_export() -> Response:
        """Download the entire library as a JSON file the user can back up,
        share with a teammate, or commit to a private repo."""
        lib = state.open_library()
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

    @router.get("/api/library/export.md")
    def library_export_markdown() -> Response:
        """Markdown view of the library — git-friendly, human-readable."""
        lib = state.open_library()
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

    @router.get("/api/library/health")
    def library_health(stale_days: int = 90) -> dict:
        """Surface duplicates / low-confidence / stale terms for cleanup."""
        lib = state.open_library()
        try:
            return lib.health_check(stale_days=stale_days)
        finally:
            lib.close()

    @router.post("/api/library/import")
    def library_import(payload: dict) -> dict:
        """Merge an exported library back in. Caller passes the parsed JSON.

        Returns the merge summary (terms_added, terms_merged, etc.).
        """
        lib = state.open_library()
        try:
            try:
                summary = lib.import_dict(payload)
            except ValueError as exc:
                raise HTTPException(400, str(exc)) from exc
            return {"summary": summary}
        finally:
            lib.close()

    # ============ Speakers ============

    @router.get("/api/library/speakers")
    def list_speakers_endpoint(search: str | None = None, limit: int = 500) -> dict:
        lib = state.open_library()
        try:
            return {"speakers": lib.list_speakers(search=search, limit=limit)}
        finally:
            lib.close()

    @router.post("/api/library/speakers", status_code=201)
    def add_speaker_endpoint(payload: SpeakerPayload) -> dict:
        if not payload.canonical_name.strip() or not payload.display_label.strip():
            raise HTTPException(400, "canonical_name and display_label are required")
        lib = state.open_library()
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

    @router.patch("/api/library/speakers/{speaker_id}")
    def update_speaker_endpoint(speaker_id: int, payload: SpeakerPayload) -> dict:
        lib = state.open_library()
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

    @router.delete("/api/library/speakers/{speaker_id}", status_code=204)
    def delete_speaker_endpoint(speaker_id: int) -> Response:
        lib = state.open_library()
        try:
            lib.delete_speaker(speaker_id)
            return Response(status_code=204)
        finally:
            lib.close()

    # ============ Edit patterns ============

    @router.get("/api/library/patterns")
    def list_patterns_endpoint(domain: str | None = None) -> dict:
        lib = state.open_library()
        try:
            return {"patterns": lib.list_edit_patterns(domain=domain)}
        finally:
            lib.close()

    @router.post("/api/library/patterns", status_code=201)
    def add_pattern_endpoint(payload: PatternPayload) -> dict:
        lib = state.open_library()
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

    @router.delete("/api/library/patterns/{pattern_id}", status_code=204)
    def delete_pattern_endpoint(pattern_id: int) -> Response:
        lib = state.open_library()
        try:
            lib.delete_edit_pattern(pattern_id)
            return Response(status_code=204)
        finally:
            lib.close()

    # ============ Negatives ============

    @router.get("/api/library/negatives")
    def list_negatives_endpoint() -> dict:
        lib = state.open_library()
        try:
            return {"negatives": lib.list_negatives()}
        finally:
            lib.close()

    @router.post("/api/library/negatives", status_code=201)
    def add_negative_endpoint(payload: NegativePayload) -> dict:
        if not payload.text.strip():
            raise HTTPException(400, "text is required")
        lib = state.open_library()
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

    @router.delete("/api/library/negatives/{negative_id}", status_code=204)
    def delete_negative_endpoint(negative_id: int) -> Response:
        lib = state.open_library()
        try:
            deleted = lib.delete_negative(negative_id)
            if not deleted:
                raise HTTPException(404, f"Negative rule {negative_id} not found")
            return Response(status_code=204)
        finally:
            lib.close()

    # ============ Persistent suggestions inbox ============
    #
    # Mode B emits suggestions per-run, persisted as suggestions.json under
    # each project. Without aggregation, a user who runs 10 transcripts has
    # to drill into each project to harvest. The inbox endpoint walks all
    # projects, merges suggestions by (kind, canonical/canonical_name/title),
    # filters out ones already in the library, and tracks per-user
    # dismissals via a small JSON sidecar in DATA_DIR.

    def _dismissed_path() -> Path:
        return state.cfg().library_path.parent / "dismissed_suggestions.json"

    def _read_dismissed() -> set[tuple[str, str]]:
        p = _dismissed_path()
        if not p.is_file():
            return set()
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
            # TypeError covers valid-JSON-wrong-shape (top-level dict,
            # list of strings, etc.) which used to 500 the inbox.
            return {(d["kind"], d["identity"]) for d in data}
        except (json.JSONDecodeError, OSError, KeyError, TypeError):
            return set()

    def _write_dismissed(items: set[tuple[str, str]]) -> None:
        # Atomic write so a crash mid-write can't corrupt the file and
        # silently resurrect every dismissed suggestion.
        target = _dismissed_path()
        payload = json.dumps(
            [{"kind": k, "identity": i} for k, i in sorted(items)],
            ensure_ascii=False,
            indent=2,
        )
        tmp = target.with_suffix(".json.tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, target)

    def _suggestion_identity(s: dict) -> str | None:
        ident = s.get("canonical") or s.get("canonical_name") or s.get("title") or ""
        return str(ident).strip() or None

    def _already_in_library(lib: Library, s: dict) -> bool:
        kind = str(s.get("kind", "")).lower()
        if kind == "term":
            canonical = (s.get("canonical") or "").strip()
            if not canonical:
                return False
            return lib.lookup_alias(canonical) is not None
        if kind == "speaker":
            canonical = (s.get("canonical_name") or "").strip()
            if not canonical:
                return False
            return lib.lookup_speaker(canonical) is not None
        # Patterns are harder to detect dupes for; treat them as never in
        # library (user can dismiss explicitly).
        return False

    @router.get("/api/library/suggestions/inbox")
    def suggestions_inbox() -> dict:
        """Aggregate pending suggestions across every project.

        For each unique (kind, identity) we collect:
        - the suggestion fields (canonical, aliases_seen, etc.)
        - ``times_seen``: how many runs surfaced this one
        - ``source_slugs``: which projects suggested it
        Already-in-library and explicitly-dismissed suggestions are excluded.
        """
        store = ProjectStore(state.cfg().projects_root)
        dismissed = _read_dismissed()
        merged: dict[tuple[str, str], dict] = {}

        lib = state.open_library()
        try:
            for summary in store.list_summaries(limit=1000):
                slug = summary["slug"]
                project = store.open(slug)
                if not project.suggestions_path.is_file():
                    continue
                try:
                    items = json.loads(project.suggestions_path.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError):
                    continue
                if not isinstance(items, list):
                    continue
                for s in items:
                    if not isinstance(s, dict):
                        continue
                    kind = str(s.get("kind", "")).lower()
                    identity = _suggestion_identity(s)
                    if not kind or not identity:
                        continue
                    key = (kind, identity.lower())
                    if key in dismissed:
                        continue
                    if _already_in_library(lib, s):
                        continue
                    if key in merged:
                        existing = merged[key]
                        existing["times_seen"] = (existing.get("times_seen") or 1) + 1
                        existing_slugs = existing.setdefault("source_slugs", [])
                        if slug not in existing_slugs:
                            existing_slugs.append(slug)
                        # Union aliases_seen if both have them.
                        new_aliases = s.get("aliases_seen") or []
                        if new_aliases:
                            seen = set(existing.get("aliases_seen") or [])
                            for a in new_aliases:
                                if a not in seen:
                                    existing.setdefault("aliases_seen", []).append(a)
                                    seen.add(a)
                    else:
                        merged[key] = {
                            **s,
                            "kind": kind,
                            "times_seen": 1,
                            "source_slugs": [slug],
                        }
        finally:
            lib.close()

        # Sort: most-seen first, then alphabetic for stability.
        out = sorted(
            merged.values(),
            key=lambda x: (
                -(x.get("times_seen") or 0),
                str(_suggestion_identity(x) or "").lower(),
            ),
        )
        return {"suggestions": out, "count": len(out)}

    @router.post("/api/library/suggestions/inbox/dismiss")
    def suggestions_inbox_dismiss(payload: dict) -> dict:
        """Mark a (kind, identity) pair as dismissed so it stops appearing
        in the inbox. The user can still find it in the source project's
        suggestions.json — dismissal only affects the inbox view.
        """
        kind = str(payload.get("kind", "")).lower().strip()
        identity = str(payload.get("identity", "")).strip()
        if not kind or not identity:
            raise HTTPException(400, "kind and identity are required")
        dismissed = _read_dismissed()
        dismissed.add((kind, identity.lower()))
        _write_dismissed(dismissed)
        return {"dismissed_count": len(dismissed)}

    @router.delete("/api/library/suggestions/inbox/dismissed", status_code=204)
    def suggestions_inbox_clear_dismissals() -> Response:
        """Reset the dismissed-suggestions set — used when the user wants
        to re-review everything (e.g. after a library cleanup).
        """
        p = _dismissed_path()
        if p.is_file():
            p.unlink()
        return Response(status_code=204)

    # ============ Accept Mode B / bootstrap suggestions ============

    @router.post("/api/library/accept-suggestions")
    def accept_suggestions(req: AcceptSuggestionsRequest) -> dict:
        lib = state.open_library()
        accepted = {"terms": 0, "speakers": 0, "patterns": 0, "skipped": 0}
        try:
            for s in req.suggestions:
                kind = s.kind.lower()
                # "jargon" comes from the bootstrap extractor — it's a term
                # with a default type. Without this branch, bootstrap's
                # jargon candidates were silently counted as "skipped".
                if kind in ("term", "jargon") and s.canonical:
                    lib.add_term(
                        canonical=s.canonical,
                        type_=s.type or ("jargon" if kind == "jargon" else None),
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

    return router

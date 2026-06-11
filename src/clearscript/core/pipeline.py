"""Minimum-viable pipeline (v0.0.6).

Single-pass: ingest → compose prompts → call LLM (chunk-by-chunk if long) →
parse output → stitch.

Library integration:
- Mode A (project-start activation): briefing text is scanned for entity hints
  (companies/products/speakers); each is looked up in the library and any
  matching aliases / related canonicals are added to the library_context block
  in the system prompt.
- Mode B (end-of-session harvest): the LLM is asked to emit a SUGGESTIONS
  block alongside the change log; pipeline parses it and exposes via
  ``EditResult.suggestions`` so the UI can ask the user to accept them.
- Mode C (in-flight learning): not in v0.0.x — needs the multi-stage pipeline
  with batch-ask. Tracked for v0.0.7+.

Chunking (v0.0.6):
- ``Pipeline.run_on_transcript`` analyzes the input and, if it would exceed
  ``trigger_tokens`` (default 6000), splits it at speaker-turn boundaries
  into chunks of ``~target_tokens`` (default 3500) and processes each
  through the same prompts. Outputs are stitched: edited markdown is
  concatenated, change logs are merged, suggestions are deduped by kind
  and canonical.
- Each chunk receives the same library context (briefing-derived seeds +
  recurring-speaker mappings). Cross-chunk learning (where chunk N's
  confirmations feed chunk N+1's prompt) is deferred to v0.0.7's Mode C.

The full multi-stage pipeline contract lives in ``docs/architecture.md``.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from clearscript.core.chunking import (
    DEFAULT_HARD_MAX_TOKENS,
    DEFAULT_TARGET_TOKENS,
    DEFAULT_TRIGGER_TOKENS,
    plan_chunks,
)
from clearscript.ingest import NormalizedTranscript, parse
from clearscript.prompts import compose_edit_prompt
from clearscript.providers import ChatMessage, LLMProvider

if TYPE_CHECKING:
    from clearscript.library import Library


@dataclass
class StreamEvent:
    """One event emitted by the streaming pipeline.

    The frontend renders ``plan`` to size the progress bar, ``chunk_start``
    / ``chunk_done`` to advance it (with running diff and token counters),
    ``complete`` to render the final EditResult, and ``error`` for failures.
    """

    name: str
    data: dict[str, object]


@dataclass
class EditResult:
    edited_markdown: str
    change_log: list[dict[str, object]] = field(default_factory=list)
    suggestions: list[dict[str, object]] = field(default_factory=list)
    raw_response: str = ""
    input_tokens: int = 0
    output_tokens: int = 0
    model: str = ""
    provider: str = ""
    num_chunks: int = 1

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


CHANGELOG_DELIMITER = "---CHANGELOG---"
SUGGESTIONS_DELIMITER = "---SUGGESTIONS---"

# Heuristic: extract candidate entities from briefing text.
_ENTITY_PATTERN = re.compile(
    r"[A-Z][a-zA-Z0-9]{2,}(?:[A-Z][a-zA-Z0-9]+)*"
    r"|[A-Z]{2,}(?:-?\d+)?"
    r"|[一-鿿]{2,4}"
)


@dataclass
class Pipeline:
    provider: LLMProvider
    model: str
    library: Library | None = None
    briefing_context: str = ""
    temperature: float = 0.0
    max_tokens: int = 16384
    chunk_target_tokens: int = DEFAULT_TARGET_TOKENS
    chunk_trigger_tokens: int = DEFAULT_TRIGGER_TOKENS
    chunk_hard_max_tokens: int = DEFAULT_HARD_MAX_TOKENS
    # Self-review is a 2nd LLM pass that re-reads the stitched output and
    # flags missed corrections / inconsistencies / over-corrections. ~1
    # extra LLM call per Run (not per chunk). Defaults to ON because the
    # quality lift is the moat — user explicitly opted into clearscript
    # over ChatGPT for the associative reasoning, and self-review is where
    # most of that reasoning lands.
    enable_self_review: bool = True
    # Skip self-review automatically if the stitched output exceeds this
    # many characters (≈25k tokens) — past this size the second call
    # gets expensive and the per-chunk Mode-C learning already provides
    # most of the cross-chunk consistency we'd get.
    self_review_max_chars: int = 100_000

    def run(self, input_path: Path) -> EditResult:
        transcript = parse(input_path)
        return self.run_on_transcript(transcript)

    def run_on_transcript(self, transcript: NormalizedTranscript) -> EditResult:
        """Synchronous entry point. Returns the final EditResult.

        Internally drives the same generator as ``iter_events`` but discards
        intermediate events. Useful for CLI / scripting / tests.
        """
        final: EditResult | None = None
        for event in self.iter_events(transcript):
            if event.name == "complete":
                final = event.data["result"]  # type: ignore[assignment]
            elif event.name == "error":
                raise RuntimeError(str(event.data.get("detail", "pipeline error")))
        if final is None:
            raise RuntimeError("pipeline ended without a complete event")
        return final

    def iter_events(self, transcript: NormalizedTranscript) -> Iterator[StreamEvent]:
        """Yield events as the pipeline progresses chunk-by-chunk.

        Event sequence:
          plan         — once, with num_chunks and total tokens
          chunk_start  — for each chunk
          chunk_done   — for each chunk, with that chunk's edited markdown,
                         change count, and token usage
          complete     — once at the end, with the final stitched EditResult
          error        — on failure (terminates the stream)
        """
        try:
            plan = plan_chunks(
                transcript,
                target_tokens=self.chunk_target_tokens,
                trigger_tokens=self.chunk_trigger_tokens,
                hard_max_tokens=self.chunk_hard_max_tokens,
            )
        except Exception as exc:
            yield StreamEvent("error", {"detail": f"chunk planning failed: {exc}"})
            return

        yield StreamEvent(
            "plan",
            {
                "num_chunks": plan.num_chunks,
                "total_input_tokens_estimate": plan.total_tokens,
            },
        )

        edited_parts: list[str] = []
        all_changes: list[dict[str, object]] = []
        all_suggestions: list[dict[str, object]] = []
        total_input_tokens = 0
        total_output_tokens = 0
        last_model = ""
        last_provider = ""

        # Mode C — cross-chunk learning: substitutions confirmed by the model
        # in earlier chunks of this run get propagated to later chunks so the
        # same alias→canonical decision doesn't have to be re-discovered.
        runtime_mappings: dict[str, str] = {}

        for idx, chunk in enumerate(plan.chunks, start=1):
            yield StreamEvent(
                "chunk_start",
                {
                    "chunk": idx,
                    "total": plan.num_chunks,
                },
            )
            try:
                # Drive the chunk through the streaming provider API so the UI
                # can show text appearing in real time. Each delta is forwarded
                # as a chunk_delta SSE event; only the final 'done' carries the
                # full ChatResponse with usage.
                accumulated = ""
                response = None
                messages = self._build_messages(
                    chunk,
                    runtime_mappings=runtime_mappings,
                    chunk_index=idx,
                    chunk_total=plan.num_chunks,
                )
                for kind, payload in self.provider.chat_with_progress(
                    messages,
                    self.model,
                    temperature=self.temperature,
                    max_tokens=self.max_tokens,
                ):
                    if kind == "delta":
                        accumulated += str(payload)
                        yield StreamEvent(
                            "chunk_delta",
                            {
                                "chunk": idx,
                                "total": plan.num_chunks,
                                "delta": payload,
                                "chars_so_far": len(accumulated),
                            },
                        )
                    elif kind == "done":
                        response = payload  # ChatResponse
                if response is None:
                    yield StreamEvent(
                        "error",
                        {"detail": f"chunk {idx} stream ended without 'done' event"},
                    )
                    return
                edited, changelog, suggestions = self._split_output(response.text)  # type: ignore[attr-defined]
                chunk_result = EditResult(
                    edited_markdown=edited,
                    change_log=changelog,
                    suggestions=suggestions,
                    raw_response=response.text,  # type: ignore[attr-defined]
                    input_tokens=response.input_tokens,  # type: ignore[attr-defined]
                    output_tokens=response.output_tokens,  # type: ignore[attr-defined]
                    model=response.model,  # type: ignore[attr-defined]
                    provider=response.provider,  # type: ignore[attr-defined]
                )
            except Exception as exc:
                yield StreamEvent(
                    "error",
                    {
                        "detail": f"chunk {idx} failed: {exc}",
                        "chunk": idx,
                        "total": plan.num_chunks,
                    },
                )
                return

            # Tag each change with chunk index for downstream audit
            for change in chunk_result.change_log:
                if "chunk" not in change:
                    change["chunk"] = idx
                all_changes.append(change)
            all_suggestions.extend(chunk_result.suggestions)
            edited_parts.append(chunk_result.edited_markdown.strip())
            total_input_tokens += chunk_result.input_tokens
            total_output_tokens += chunk_result.output_tokens
            last_model = chunk_result.model
            last_provider = chunk_result.provider

            # Mode C: harvest L3 (ASR fix) substitutions from this chunk so
            # the next chunk's prompt knows "we already decided X → Y here".
            # Filter aggressively: only short before/after pairs that look
            # like proper-noun substitutions, not entire-sentence rewrites.
            for change in chunk_result.change_log:
                layer = str(change.get("layer", "")).upper()
                before = str(change.get("before") or "").strip()
                after = str(change.get("after") or "").strip()
                if (
                    layer.startswith("L3")
                    and before
                    and after
                    and before != after
                    and 1 <= len(before) <= 30
                    and 1 <= len(after) <= 30
                ):
                    runtime_mappings.setdefault(before, after)

            yield StreamEvent(
                "chunk_done",
                {
                    "chunk": idx,
                    "total": plan.num_chunks,
                    "edited_partial": chunk_result.edited_markdown,
                    "changes_in_chunk": len(chunk_result.change_log),
                    "changes_so_far": len(all_changes),
                    "suggestions_so_far": len(all_suggestions),
                    "input_tokens": chunk_result.input_tokens,
                    "output_tokens": chunk_result.output_tokens,
                    "input_tokens_so_far": total_input_tokens,
                    "output_tokens_so_far": total_output_tokens,
                },
            )

        stitched = "\n\n".join(p for p in edited_parts if p)
        deduped_suggestions = _dedupe_suggestions(all_suggestions)

        # ============ Self-review (2nd pass on stitched output) ============
        # Re-read the cleaned transcript and flag missed corrections,
        # inconsistencies, over-corrections. ~30% more L3 errors caught on
        # average. Costs one extra LLM call per run (not per chunk).
        # Skip on huge outputs to keep cost bounded.
        review_changes: list[dict[str, object]] = []
        review_input_tokens = 0
        review_output_tokens = 0
        review_diagnostics: dict[str, object] = {}
        if (
            self.enable_self_review
            and stitched
            and len(stitched) <= self.self_review_max_chars
        ):
            yield StreamEvent(
                "self_review_start",
                {"chars": len(stitched), "model": self.model},
            )
            try:
                review_result = self._run_self_review(
                    stitched_markdown=stitched,
                    change_log=all_changes,
                )
                review_input_tokens = review_result["input_tokens"]
                review_output_tokens = review_result["output_tokens"]
                review_diagnostics = review_result["diagnostics"]
                # Apply additional_corrections to the stitched markdown.
                # Guards (each one is a bug we shipped or nearly shipped):
                #   - empty/missing 'new' → would silently DELETE text; route
                #     to user-review diagnostics instead of applying
                #   - 'old' occurring more than once → replace(…, 1) might hit
                #     the wrong occurrence; route to user-review instead
                skipped_ambiguous: list[dict[str, object]] = []
                for change in review_result["additional_corrections"]:
                    old = str(change.get("old") or "")
                    new = str(change.get("new") or "")
                    if not old or old == new:
                        continue
                    if not new.strip():
                        skipped_ambiguous.append(
                            {
                                "location": f"text {old[:60]!r}",
                                "issue": "self-review proposed deleting this text outright",
                                "options": ["keep original", "delete"],
                            }
                        )
                        continue
                    occurrences = stitched.count(old)
                    if occurrences == 0:
                        continue
                    if occurrences > 1:
                        skipped_ambiguous.append(
                            {
                                "location": f"text {old[:60]!r} ({occurrences} occurrences)",
                                "issue": f"self-review correction to {new[:60]!r} is ambiguous "
                                "— the original appears multiple times",
                                "options": [old, new],
                            }
                        )
                        continue
                    stitched = stitched.replace(old, new, 1)
                    change.setdefault("stage", "self_review")
                    review_changes.append(change)
                if skipped_ambiguous:
                    promotions = review_diagnostics.setdefault(
                        "promotions_to_user_review", []
                    )
                    if isinstance(promotions, list):
                        promotions.extend(skipped_ambiguous)

                total_input_tokens += review_input_tokens
                total_output_tokens += review_output_tokens
                all_changes.extend(review_changes)

                yield StreamEvent(
                    "self_review_done",
                    {
                        "additional_changes": len(review_changes),
                        "rollbacks_flagged": len(review_diagnostics.get("rollbacks", []) or []),
                        "promotions": len(review_diagnostics.get("promotions_to_user_review", []) or []),
                        "data_conflicts": len(review_diagnostics.get("data_conflicts", []) or []),
                        "input_tokens": review_input_tokens,
                        "output_tokens": review_output_tokens,
                    },
                )
            except Exception as exc:
                # Self-review is opportunistic — never fail the run if it
                # explodes. Surface the error to the UI so the user knows
                # they got first-pass output only.
                yield StreamEvent(
                    "self_review_error",
                    {"detail": f"self-review skipped: {exc}"},
                )

        result = EditResult(
            edited_markdown=stitched,
            change_log=all_changes,
            suggestions=deduped_suggestions,
            raw_response="",
            input_tokens=total_input_tokens,
            output_tokens=total_output_tokens,
            model=last_model,
            provider=last_provider,
            num_chunks=plan.num_chunks,
        )

        yield StreamEvent(
            "complete",
            {
                "result": result,
                # Also flatten the result so SSE consumers can access fields
                # without unpacking the dataclass:
                "edited_markdown": result.edited_markdown,
                "change_log": result.change_log,
                "suggestions": result.suggestions,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "model": result.model,
                "provider": result.provider,
                "num_chunks": result.num_chunks,
                # Surface self-review diagnostics so the UI can show flags
                # the user should look at (data conflicts, promoted items).
                "self_review": review_diagnostics if review_diagnostics else None,
            },
        )

    def _build_messages(
        self,
        chunk: NormalizedTranscript,
        *,
        runtime_mappings: dict[str, str] | None = None,
        chunk_index: int = 1,
        chunk_total: int = 1,
    ) -> list[ChatMessage]:
        """Build the system + user message pair for one chunk's LLM call.

        ``runtime_mappings`` carries Mode-C decisions from earlier chunks
        (alias → canonical pairs the model already committed to). Pass it
        through so the system prompt can mention them and the model stays
        consistent across the whole transcript.

        ``chunk_index``/``chunk_total`` tell L2 whether this chunk contains
        the real head/tail of the transcript. Without them, L2 trimmed
        "opening pleasantries" off the start of EVERY chunk — deleting
        mid-transcript content on long recordings.
        """
        library_context = self._collect_library_context(
            chunk, runtime_mappings=runtime_mappings
        )
        system_prompt = compose_edit_prompt(
            briefing_context=self.briefing_context,
            library_context=library_context,
        )
        return [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(
                role="user",
                content=self._build_user_prompt(
                    chunk, chunk_index=chunk_index, chunk_total=chunk_total
                ),
            ),
        ]

    def _run_single_chunk(self, chunk: NormalizedTranscript) -> EditResult:
        library_context = self._collect_library_context(chunk)
        system_prompt = compose_edit_prompt(
            briefing_context=self.briefing_context,
            library_context=library_context,
        )

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=self._build_user_prompt(chunk)),
        ]

        response = self.provider.chat(
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        edited, changelog, suggestions = self._split_output(response.text)

        return EditResult(
            edited_markdown=edited,
            change_log=changelog,
            suggestions=suggestions,
            raw_response=response.text,
            input_tokens=response.input_tokens,
            output_tokens=response.output_tokens,
            model=response.model,
            provider=response.provider,
        )

    def _run_self_review(
        self,
        *,
        stitched_markdown: str,
        change_log: list[dict[str, object]],
    ) -> dict:
        """Single LLM call: re-read the stitched output and flag missed
        corrections / inconsistencies / over-corrections.

        Returns a dict with:
          - ``additional_corrections``: list of {old, new, reason, ...}
            ready to be applied to the markdown
          - ``diagnostics``: rollbacks, promotions_to_user_review,
            data_conflicts, format_issues — for the UI to surface
          - ``input_tokens`` / ``output_tokens``: real usage

        Failures (model returned garbage, JSON parse error, etc.) bubble
        up — the caller wraps in try/except and skips the pass if it
        explodes, never blocking the main result.
        """
        from clearscript.prompts import compose_self_review_prompt

        system_prompt = compose_self_review_prompt()
        # Build the library context fresh — the review pass needs the
        # full vocabulary too so it can catch missed proper nouns.
        library_block = ""
        if self.library is not None:
            try:
                all_terms = self.library.list_terms(limit=200)
                vocab_lines = []
                for t in all_terms:
                    if t.get("status") == "deprecated":
                        continue
                    canonical = t.get("canonical")
                    if not canonical:
                        continue
                    aliases = t.get("aliases") or []
                    alias_str = ", ".join(f"`{a}`" for a in aliases) if aliases else "—"
                    type_str = f" [{t.get('type')}]" if t.get("type") else ""
                    vocab_lines.append(f"- **{canonical}**{type_str} ← {alias_str}")
                if vocab_lines:
                    library_block = (
                        "Your full vocabulary (canonical ← aliases). Audit "
                        "the document for any phonetic neighbour of these "
                        "that the first pass left uncorrected:\n"
                        + "\n".join(vocab_lines)
                    )
            except Exception:
                library_block = ""

        # Plain sections rather than JSON-wrapping the whole transcript:
        # double-encoding the document inside a JSON string escaped every
        # quote/newline (token-expensive) and tied review quality to the
        # model's willingness to read a giant string literal.
        changelog_json = json.dumps(change_log[:200], ensure_ascii=False)
        briefing_part = (
            f"## Session briefing\n\n{self.briefing_context}\n\n" if self.briefing_context else ""
        )
        library_part = f"## Library vocabulary\n\n{library_block}\n\n" if library_block else ""
        user_msg = (
            "Run the self-review routine. Output the JSON object specified "
            "in the system prompt — raw JSON preferred; a ```json fence is "
            "tolerated but add no other prose.\n\n"
            f"{briefing_part}"
            f"{library_part}"
            "## First-pass change log (JSON)\n\n"
            f"{changelog_json}\n\n"
            "## Cleaned transcript (between the markers; do NOT echo it back)\n\n"
            "<<<TRANSCRIPT_START>>>\n"
            f"{stitched_markdown}\n"
            "<<<TRANSCRIPT_END>>>"
        )

        messages = [
            ChatMessage(role="system", content=system_prompt),
            ChatMessage(role="user", content=user_msg),
        ]
        response = self.provider.chat(
            messages,
            model=self.model,
            temperature=self.temperature,
            max_tokens=self.max_tokens,
        )

        # Parse the JSON object the model returned.
        text = self._strip_json_fence(response.text)
        # The output is supposed to be a single object, not a list. Try
        # parsing as object first; if the model wrapped in a list, take [0].
        try:
            parsed = json.loads(text)
            if isinstance(parsed, list) and parsed:
                parsed = parsed[0]
        except json.JSONDecodeError:
            # Don't silently swallow garbage into "no findings" — raise so
            # the caller emits self_review_error and the user knows they
            # got first-pass output only.
            raise ValueError(
                f"self-review returned unparseable output ({len(response.text)} chars)"
            ) from None
        if not isinstance(parsed, dict):
            parsed = {}

        additional = parsed.get("additional_corrections") or []
        if not isinstance(additional, list):
            additional = []
        additional = [c for c in additional if isinstance(c, dict)]

        diagnostics = {
            "rollbacks": parsed.get("rollbacks") or [],
            "promotions_to_user_review": parsed.get("promotions_to_user_review") or [],
            "data_conflicts": parsed.get("data_conflicts") or [],
            "format_issues": parsed.get("format_issues") or [],
        }

        return {
            "additional_corrections": additional,
            "diagnostics": diagnostics,
            "input_tokens": response.input_tokens,
            "output_tokens": response.output_tokens,
        }

    # Note: the legacy ``_run_multi_chunk`` is now subsumed by ``iter_events``.
    # ``run_on_transcript`` consumes the event stream and returns the final
    # EditResult — see ``iter_events`` above.

    def _build_user_prompt(
        self,
        transcript: NormalizedTranscript,
        *,
        chunk_index: int = 1,
        chunk_total: int = 1,
    ) -> str:
        # L2 head/tail trimming must only fire on the actual head/tail of
        # the recording. On middle chunks the "start" is mid-conversation —
        # trimming it would delete real content.
        if chunk_total <= 1:
            position_note = ""
        else:
            is_first = chunk_index == 1
            is_last = chunk_index == chunk_total
            if is_first:
                scope = (
                    "This is the FIRST chunk: L2 may trim opening pleasantries "
                    "at the START, but the end of this chunk is mid-conversation "
                    "— do NOT trim anything from the end."
                )
            elif is_last:
                scope = (
                    "This is the LAST chunk: L2 may trim closing farewells at "
                    "the END, but the start of this chunk is mid-conversation "
                    "— do NOT trim anything from the start."
                )
            else:
                scope = (
                    "This is a MIDDLE chunk: both its start and end are "
                    "mid-conversation. L2 head/tail trimming does NOT apply — "
                    "only strip embedded AI-summary blocks if present."
                )
            position_note = (
                f"\n\nChunk position: {chunk_index} of {chunk_total}. {scope}"
            )
        return (
            "Apply the layered edit pipeline (L1 through L6, including L3.5) to the transcript "
            "below. Output the cleaned markdown transcript first, then the line "
            f"`{CHANGELOG_DELIMITER}` on its own line, then the JSON change log, then the line "
            f"`{SUGGESTIONS_DELIMITER}`, then the JSON list of library suggestions."
            f"{position_note}\n\n"
            "Raw transcript:\n\n"
            "```\n"
            f"{transcript.to_markdown()}\n"
            "```"
        )

    def _collect_library_context(
        self,
        transcript: NormalizedTranscript,
        *,
        runtime_mappings: dict[str, str] | None = None,
    ) -> str:
        """Build the library-context block sent in the system prompt.

        Lookups, in order of priority:

        1. **Detected speakers** in this chunk — match against the speakers
           table so the model uses canonical names.
        2. **Entities in the transcript itself** — this is the one that
           actually catches "Tabby" in the raw text. Previously we only
           scanned the briefing, so a user with no briefing got an empty
           library context and the seed pack was effectively dead weight.
        3. **Entities in the briefing** — additional hints from context the
           user provided up front.
        4. **Mode-C runtime mappings** — substitutions already committed
           to in earlier chunks of this run.

        Capped at a sane number of term lines to keep the prompt small;
        otherwise a library with 500 terms could blow the context budget.
        """
        if self.library is None:
            return ""

        sections: list[str] = []
        seen_canonicals: set[str] = set()
        term_lines: list[str] = []
        briefing_speaker_lines: list[str] = []
        max_term_lines = 60

        speaker_lines: list[str] = []
        for spk in transcript.detected_speakers:
            hit = self.library.lookup_speaker(spk)
            if hit:
                speaker_lines.append(
                    f"- ASR speaker {spk!r} → use canonical label `{hit.display_label}` "
                    f"(real name: {hit.canonical_name})"
                )
        if speaker_lines:
            sections.append("Known speakers (from your library):\n" + "\n".join(speaker_lines))

        # Pass 1 — entities actually present in this chunk (or the briefing).
        # These get the high-emphasis, context-specific lines.
        for source_text in (transcript.to_markdown(), self.briefing_context or ""):
            if not source_text:
                continue
            for token in self._extract_entities(source_text):
                if len(term_lines) >= max_term_lines:
                    break
                term_hit = self.library.lookup_alias(token)
                if term_hit and term_hit.canonical not in seen_canonicals:
                    if token == term_hit.canonical:
                        # Token is already the canonical — tell the model the
                        # term exists (so it preserves spelling) but don't
                        # frame it as a substitution.
                        term_lines.append(
                            f"- {term_hit.canonical!r} is a known {term_hit.type or 'term'} "
                            f"in your library (confidence {term_hit.confidence:.2f})"
                        )
                    else:
                        term_lines.append(
                            f"- ASR may write {token!r} → canonical `{term_hit.canonical}` "
                            f"({term_hit.type or 'term'}, confidence {term_hit.confidence:.2f})"
                        )
                    seen_canonicals.add(term_hit.canonical)
                    continue
                spk_hit = self.library.lookup_speaker(token)
                if spk_hit and spk_hit.canonical_name not in seen_canonicals:
                    briefing_speaker_lines.append(
                        f"- {token!r} → speaker label `{spk_hit.display_label}` "
                        f"(real name: {spk_hit.canonical_name})"
                    )
                    seen_canonicals.add(spk_hit.canonical_name)

        if term_lines:
            sections.append("Term mappings from your library:\n" + "\n".join(term_lines))
        if briefing_speaker_lines:
            sections.append(
                "Speakers mentioned in context, found in your library:\n"
                + "\n".join(briefing_speaker_lines)
            )

        # Pass 2 — VOCAB PRIMER: the rest of the vocabulary (canonical +
        # every alias) so the model can phonetic-match NEW misspellings the
        # regex extractor can't catch (transcript says "Tabbey", library
        # only knows "Tabby" → "Tavily"). Filter deprecated BEFORE the cap
        # so dead entries don't consume slots, rank by usage so a large
        # library keeps its most load-bearing terms, and exclude canonicals
        # already emphasised in Pass 1 to avoid paying for them twice.
        vocab_lines: list[str] = []
        try:
            all_terms = self.library.list_terms(limit=500)
        except Exception:
            all_terms = []
        active_terms = [
            t
            for t in all_terms
            if t.get("status") != "deprecated"
            and t.get("canonical")
            and t["canonical"] not in seen_canonicals
        ]
        active_terms.sort(
            key=lambda t: (-(t.get("times_used") or 0), str(t["canonical"]).lower())
        )
        for t in active_terms[:200]:
            aliases = t.get("aliases") or []
            alias_str = ", ".join(f"`{a}`" for a in aliases) if aliases else "—"
            type_str = f" [{t.get('type')}]" if t.get("type") else ""
            vocab_lines.append(f"- **{t['canonical']}**{type_str} ← {alias_str}")
        if vocab_lines:
            sections.append(
                "Your full vocabulary (canonical ← known ASR variants). "
                "Watch for any of these forms — AND any phonetic neighbours "
                "of these canonicals — in the transcript:\n"
                + "\n".join(vocab_lines)
            )

        if runtime_mappings:
            mapping_lines = [
                f"- {before!r} → `{after}`"
                for before, after in list(runtime_mappings.items())[:40]
            ]
            sections.append(
                "Earlier chunks in this same run already substituted these — "
                "stay consistent:\n" + "\n".join(mapping_lines)
            )

        return "\n\n".join(sections)

    @staticmethod
    def _extract_entities(text: str) -> list[str]:
        """Heuristic extraction of candidate entity tokens from briefing text."""
        seen: set[str] = set()
        ordered: list[str] = []
        for match in _ENTITY_PATTERN.finditer(text):
            token = match.group(0).strip()
            if len(token) < 2 or token in seen:
                continue
            if token.lower() in {"the", "and", "for", "with", "from", "into", "this", "that"}:
                continue
            seen.add(token)
            ordered.append(token)
        return ordered

    @staticmethod
    def _strip_json_fence(text: str) -> str:
        """Remove markdown code-fence wrapping if the model added it."""
        text = text.strip()
        if text.startswith("```"):
            lines = [line for line in text.splitlines() if not line.startswith("```")]
            text = "\n".join(lines).strip()
        return text

    @classmethod
    def _split_output(
        cls, text: str
    ) -> tuple[str, list[dict[str, object]], list[dict[str, object]]]:
        """Parse the model's three-section response: markdown / changelog / suggestions."""
        if CHANGELOG_DELIMITER not in text:
            return text.strip(), [], []

        edited_part, _, after_changelog = text.partition(CHANGELOG_DELIMITER)
        edited = edited_part.strip()

        if SUGGESTIONS_DELIMITER in after_changelog:
            changelog_part, _, suggestions_part = after_changelog.partition(SUGGESTIONS_DELIMITER)
        else:
            changelog_part = after_changelog
            suggestions_part = "[]"

        changelog = cls._parse_json_list(changelog_part)
        suggestions = cls._parse_json_list(suggestions_part)
        return edited, changelog, suggestions

    @classmethod
    def _parse_json_list(cls, text: str) -> list[dict[str, object]]:
        cleaned = cls._strip_json_fence(text)
        if not cleaned:
            return []
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            return []
        if isinstance(parsed, list):
            return [item for item in parsed if isinstance(item, dict)]
        return []


def _dedupe_suggestions(items: list[dict[str, object]]) -> list[dict[str, object]]:
    """Merge duplicate suggestions across chunks by kind + canonical/title."""
    seen_keys: set[tuple[str, str]] = set()
    out: list[dict[str, object]] = []
    for item in items:
        kind = str(item.get("kind", "")).lower()
        identity = item.get("canonical") or item.get("canonical_name") or item.get("title") or ""
        key = (kind, str(identity).lower())
        if not identity or key in seen_keys:
            continue
        seen_keys.add(key)
        out.append(item)
    return out

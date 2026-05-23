"""Library bootstrap — run an entity-extraction pass over a batch of past
transcripts and aggregate candidate library entries by frequency.

The user's workflow: they have N old ASR transcripts sitting in a folder.
Cleaning them one by one means the library compounds slowly — by the time
they're on transcript 6, the library finally helps. Bootstrap inverts that:
do a cheap (no-rewrite) extraction pass over all N transcripts upfront,
aggregate candidates with frequency counts, present the merged list, let
the user one-click Accept All.

This is the answer to "why use clearscript instead of ChatGPT" — the first
real cleanup is already armed with the user's full library, instead of
catching up over 10 runs.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from dataclasses import dataclass

from clearscript.core.pipeline import Pipeline, StreamEvent
from clearscript.ingest.base import NormalizedTranscript
from clearscript.prompts import compose_bootstrap_prompt
from clearscript.providers.base import ChatMessage, LLMProvider


@dataclass
class BootstrapCandidate:
    """One aggregated candidate library entry.

    Created by merging identical-canonical entries across the batch.
    Carries provenance (times_seen, transcript indices) so the UI can
    sort by frequency and the user can spot-check which transcripts
    each candidate came from.
    """

    kind: str
    canonical: str
    aliases_seen: list[str]
    type: str | None
    contexts: list[str]
    confidence: float
    times_seen: int
    transcript_indices: list[int]

    def to_suggestion_dict(self) -> dict:
        """Shape this entry for ``POST /api/library/accept-suggestions``.

        Same field names the existing accept-suggestions endpoint expects,
        so bootstrap → accept reuses the same persistence path Mode B
        suggestions go through.
        """
        out: dict = {
            "kind": self.kind,
            "aliases_seen": list(self.aliases_seen),
            "type": self.type,
        }
        if self.kind == "speaker":
            # The accept-suggestions endpoint expects canonical_name +
            # display_label for speakers. Default display_label = "<name>："
            # to match clearscript's preferred speaker tag style.
            out["canonical_name"] = self.canonical
            out["display_label"] = f"{self.canonical}："
        else:
            out["canonical"] = self.canonical
        return out


def _merge_into_aggregate(
    aggregate: dict[tuple[str, str], BootstrapCandidate],
    raw: dict,
    transcript_idx: int,
) -> None:
    """Fold one LLM-emitted candidate into the running aggregate.

    Dedup key is ``(kind, canonical.lower())`` so case-variants merge.
    Aliases and contexts are unioned; confidence is the max seen; counts
    increment by one transcript (even if the entity appeared 5× in that
    transcript — we count per-transcript, not per-mention, to avoid
    rewarding verbose speakers).
    """
    kind = str(raw.get("kind", "")).lower().strip()
    canonical = str(raw.get("canonical", "")).strip()
    if not kind or not canonical:
        return
    if kind not in {"term", "speaker", "jargon"}:
        return

    key = (kind, canonical.lower())
    aliases = [
        str(a).strip()
        for a in (raw.get("aliases_seen") or [])
        if isinstance(a, str) and a.strip()
    ]
    context = str(raw.get("context") or "").strip()
    type_ = raw.get("type")
    if type_ is not None:
        type_ = str(type_).strip() or None
    try:
        confidence = float(raw.get("confidence", 0.5))
    except (TypeError, ValueError):
        confidence = 0.5

    if key in aggregate:
        existing = aggregate[key]
        # Union aliases (preserve insertion order).
        seen_aliases = {a.lower() for a in existing.aliases_seen}
        for a in aliases:
            if a.lower() not in seen_aliases:
                existing.aliases_seen.append(a)
                seen_aliases.add(a.lower())
        if context and context not in existing.contexts:
            existing.contexts.append(context)
        # Don't count the same transcript twice if the model emitted
        # the same canonical multiple times in one input.
        if transcript_idx not in existing.transcript_indices:
            existing.transcript_indices.append(transcript_idx)
            existing.times_seen += 1
        existing.confidence = max(existing.confidence, confidence)
        if existing.type is None and type_:
            existing.type = type_
    else:
        aggregate[key] = BootstrapCandidate(
            kind=kind,
            canonical=canonical,
            aliases_seen=aliases,
            type=type_,
            contexts=[context] if context else [],
            confidence=confidence,
            times_seen=1,
            transcript_indices=[transcript_idx],
        )


def _parse_bootstrap_response(text: str) -> list[dict]:
    """Lenient JSON list parsing — tolerate model fences and stray prose.

    The bootstrap prompt asks for "just JSON, nothing else", but real
    models do sometimes wrap in ```json``` or prepend a sentence. Reuse
    the pipeline's parser, then fall back to first ``[...]`` substring.
    """
    parsed = Pipeline._parse_json_list(text)
    if parsed:
        return parsed
    # Last-resort: scan for the first balanced array.
    start = text.find("[")
    end = text.rfind("]")
    if start >= 0 and end > start:
        try:
            candidate = json.loads(text[start : end + 1])
            if isinstance(candidate, list):
                return [item for item in candidate if isinstance(item, dict)]
        except json.JSONDecodeError:
            pass
    return []


def bootstrap_from_transcripts(
    *,
    provider: LLMProvider,
    model: str,
    transcripts: list[NormalizedTranscript],
    temperature: float = 0.0,
    max_tokens: int = 4096,
) -> Iterator[StreamEvent]:
    """Run the bootstrap prompt over each transcript, aggregate, stream events.

    Events emitted:
      ``plan``               — once, with total transcript count
      ``transcript_start``   — for each transcript
      ``transcript_done``    — after each, with candidates_so_far
      ``transcript_error``   — if a single transcript fails (rest continue)
      ``complete``           — once, with the final sorted candidate list
      ``error``              — fatal: yields and stops

    The aggregation is fail-soft per transcript: one transcript that the
    model garbles into invalid JSON doesn't kill the whole bootstrap —
    we record the error and move on. A batch of 20 transcripts is
    valuable even if 2 fail.
    """
    yield StreamEvent("plan", {"num_transcripts": len(transcripts)})

    if not transcripts:
        yield StreamEvent("complete", {"candidates": [], "errors": []})
        return

    system_prompt = compose_bootstrap_prompt()
    aggregate: dict[tuple[str, str], BootstrapCandidate] = {}
    errors: list[dict] = []
    total_input_tokens = 0
    total_output_tokens = 0

    for idx, transcript in enumerate(transcripts, start=1):
        yield StreamEvent(
            "transcript_start",
            {"index": idx, "total": len(transcripts)},
        )
        try:
            messages = [
                ChatMessage(role="system", content=system_prompt),
                ChatMessage(role="user", content=transcript.to_markdown()),
            ]
            response = provider.chat(
                messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            total_input_tokens += response.input_tokens
            total_output_tokens += response.output_tokens
            raw_candidates = _parse_bootstrap_response(response.text)
        except Exception as exc:
            errors.append({"index": idx, "detail": str(exc)})
            yield StreamEvent(
                "transcript_error",
                {"index": idx, "total": len(transcripts), "detail": str(exc)},
            )
            continue

        for raw in raw_candidates:
            _merge_into_aggregate(aggregate, raw, idx)

        yield StreamEvent(
            "transcript_done",
            {
                "index": idx,
                "total": len(transcripts),
                "candidates_so_far": len(aggregate),
                "input_tokens_so_far": total_input_tokens,
                "output_tokens_so_far": total_output_tokens,
            },
        )

    # Sort: most-seen first, then confidence, then canonical (alphabetic
    # for stability). UI rendering relies on this order.
    sorted_candidates = sorted(
        aggregate.values(),
        key=lambda c: (-c.times_seen, -c.confidence, c.canonical.lower()),
    )

    yield StreamEvent(
        "complete",
        {
            "candidates": [
                {
                    "kind": c.kind,
                    "canonical": c.canonical,
                    "aliases_seen": c.aliases_seen,
                    "type": c.type,
                    "contexts": c.contexts,
                    "confidence": c.confidence,
                    "times_seen": c.times_seen,
                    "transcript_indices": c.transcript_indices,
                    # Pre-built shape for the accept-suggestions endpoint.
                    "as_suggestion": c.to_suggestion_dict(),
                }
                for c in sorted_candidates
            ],
            "errors": errors,
            "input_tokens": total_input_tokens,
            "output_tokens": total_output_tokens,
        },
    )

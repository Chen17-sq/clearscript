"""Tests for the library bootstrap pipeline.

The bootstrap pass is the killer feature that closes clearscript's
cold-start gap: user dumps N old transcripts → one extraction-only LLM
call per transcript → aggregated candidate library entries by frequency.
Tests pin the aggregation contract — alias union, per-transcript count
(not per-mention), and graceful per-transcript error handling.
"""

from __future__ import annotations

from clearscript.core.bootstrap import (
    BootstrapCandidate,
    _parse_bootstrap_response,
    bootstrap_from_transcripts,
)
from clearscript.ingest.txt import TxtAdapter
from clearscript.providers.base import ChatMessage, ChatResponse


class StubProvider:
    name = "stub-bootstrap"

    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[list[ChatMessage]] = []

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        text = self.responses.pop(0) if self.responses else "[]"
        return ChatResponse(
            text=text,
            input_tokens=100,
            output_tokens=20,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, *a, **k):  # type: ignore[no-untyped-def]
        yield ""

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield ("done", self.chat(messages, model, **kwargs))


def _txt(s: str):
    return TxtAdapter().parse_string(s)


def _run(provider, transcripts):
    return list(
        bootstrap_from_transcripts(
            provider=provider, model="m", transcripts=transcripts
        )
    )


# ============ Aggregation contract ============


def test_same_canonical_across_transcripts_merges_to_one_entry() -> None:
    """Tavily flagged in 2 separate transcripts → one entry, times_seen=2."""
    canned = (
        '[{"kind":"term","canonical":"Tavily","aliases_seen":["Tabby"],'
        '"type":"company","context":"use Tabby","confidence":0.9}]'
    )
    provider = StubProvider([canned, canned])
    events = _run(provider, [_txt("Speaker 1: Tabby."), _txt("Speaker 1: Tabby.")])
    complete = next(e for e in events if e.name == "complete")
    candidates = complete.data["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["canonical"] == "Tavily"
    assert candidates[0]["times_seen"] == 2
    assert candidates[0]["aliases_seen"] == ["Tabby"]


def test_aliases_union_across_transcripts() -> None:
    """Different aliases for the same canonical get unioned, deduped."""
    provider = StubProvider(
        [
            '[{"kind":"term","canonical":"Tavily","aliases_seen":["Tabby"],"confidence":0.9}]',
            '[{"kind":"term","canonical":"Tavily","aliases_seen":["Tably", "Tabby"],"confidence":0.7}]',
        ]
    )
    events = _run(provider, [_txt("a"), _txt("b")])
    candidates = next(e for e in events if e.name == "complete").data["candidates"]
    assert len(candidates) == 1
    aliases = candidates[0]["aliases_seen"]
    assert "Tabby" in aliases and "Tably" in aliases
    # Confidence = max seen.
    assert candidates[0]["confidence"] == 0.9


def test_per_transcript_count_not_per_mention() -> None:
    """If the model emits the same canonical twice within ONE transcript's
    output, times_seen should still increment by 1 — we count distinct
    transcripts, not mentions, to avoid rewarding verbose speakers.
    """
    provider = StubProvider(
        [
            # One transcript, but the model emits 'Tavily' twice (sloppy).
            '[{"kind":"term","canonical":"Tavily","aliases_seen":["Tabby"]},'
            '{"kind":"term","canonical":"Tavily","aliases_seen":["Tably"]}]'
        ]
    )
    events = _run(provider, [_txt("hi")])
    candidates = next(e for e in events if e.name == "complete").data["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["times_seen"] == 1
    # Aliases still get unioned within the transcript.
    assert set(candidates[0]["aliases_seen"]) == {"Tably", "Tabby"}


def test_candidates_sorted_by_frequency_desc() -> None:
    provider = StubProvider(
        [
            '[{"kind":"term","canonical":"Rare","aliases_seen":[]}]',
            '[{"kind":"term","canonical":"Common","aliases_seen":[]}]',
            '[{"kind":"term","canonical":"Common","aliases_seen":[]}]',
            '[{"kind":"term","canonical":"Common","aliases_seen":[]}]',
        ]
    )
    events = _run(provider, [_txt(f"t{i}") for i in range(4)])
    candidates = next(e for e in events if e.name == "complete").data["candidates"]
    names = [c["canonical"] for c in candidates]
    # Common should come before Rare (3 sightings vs 1).
    assert names.index("Common") < names.index("Rare")


def test_speaker_kind_produces_speaker_suggestion_shape() -> None:
    """Speaker entries need canonical_name + display_label in the
    suggestion shape so accept-suggestions persists them correctly.
    """
    provider = StubProvider(
        ['[{"kind":"speaker","canonical":"Eileen","aliases_seen":["艾琳"]}]']
    )
    events = _run(provider, [_txt("hi")])
    candidates = next(e for e in events if e.name == "complete").data["candidates"]
    s = candidates[0]["as_suggestion"]
    assert s["kind"] == "speaker"
    assert s["canonical_name"] == "Eileen"
    assert s["display_label"] == "Eileen："


def test_empty_array_response_is_fine() -> None:
    """Model returns [] for a transcript with no notable entities — that's
    valid output, not an error.
    """
    provider = StubProvider(["[]", "[]"])
    events = _run(provider, [_txt("hi"), _txt("there")])
    complete = next(e for e in events if e.name == "complete")
    assert complete.data["candidates"] == []
    assert complete.data["errors"] == []


def test_skips_malformed_entries() -> None:
    """Entries missing kind or canonical are silently dropped."""
    provider = StubProvider(
        [
            '[{"canonical":"NoKind"},'
            '{"kind":"term"},'
            '{"kind":"term","canonical":""},'
            '{"kind":"invalid-kind","canonical":"X"},'
            '{"kind":"term","canonical":"Valid","aliases_seen":[]}]'
        ]
    )
    events = _run(provider, [_txt("hi")])
    candidates = next(e for e in events if e.name == "complete").data["candidates"]
    assert len(candidates) == 1
    assert candidates[0]["canonical"] == "Valid"


# ============ Error handling ============


def test_one_failed_transcript_doesnt_kill_batch() -> None:
    """A model that returns garbage on transcript 2 of 3 — events
    continue, error is recorded, transcripts 1 and 3 still contribute.
    """

    class FlakyProvider:
        name = "flaky"

        def __init__(self) -> None:
            self.call = 0

        def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            self.call += 1
            if self.call == 2:
                raise RuntimeError("network blip")
            return ChatResponse(
                text='[{"kind":"term","canonical":"FromGood"}]',
                input_tokens=10, output_tokens=5,
                model=model, provider=self.name, latency_ms=1.0,
            )

        def stream(self, *a, **k):  # type: ignore[no-untyped-def]
            yield ""

        def chat_with_progress(self, *a, **k):  # type: ignore[no-untyped-def]
            yield ("done", self.chat(*a, **k))

    events = _run(FlakyProvider(), [_txt("a"), _txt("b"), _txt("c")])
    names = [e.name for e in events]
    assert "transcript_error" in names
    complete = next(e for e in events if e.name == "complete")
    # First + third transcript contributed; second errored out.
    assert len(complete.data["candidates"]) == 1
    assert complete.data["candidates"][0]["times_seen"] == 2
    assert len(complete.data["errors"]) == 1
    assert complete.data["errors"][0]["index"] == 2


def test_empty_transcript_list_completes_immediately() -> None:
    events = _run(StubProvider([]), [])
    assert events[-1].name == "complete"
    assert events[-1].data["candidates"] == []


# ============ Response parsing ============


def test_parse_response_handles_markdown_fence() -> None:
    text = '```json\n[{"kind":"term","canonical":"X"}]\n```'
    parsed = _parse_bootstrap_response(text)
    assert len(parsed) == 1
    assert parsed[0]["canonical"] == "X"


def test_parse_response_extracts_array_from_surrounding_prose() -> None:
    """Models sometimes prepend prose despite the system prompt — we
    fall back to finding the first balanced [...] in the output.
    """
    text = 'Here are the candidates I found:\n[{"kind":"term","canonical":"X"}]\n— done.'
    parsed = _parse_bootstrap_response(text)
    assert len(parsed) == 1
    assert parsed[0]["canonical"] == "X"


def test_parse_response_returns_empty_on_garbage() -> None:
    assert _parse_bootstrap_response("not json at all") == []
    assert _parse_bootstrap_response("") == []


# ============ BootstrapCandidate.to_suggestion_dict ============


def test_candidate_to_suggestion_dict_for_term() -> None:
    c = BootstrapCandidate(
        kind="term",
        canonical="Tavily",
        aliases_seen=["Tabby"],
        type="company",
        contexts=[],
        confidence=0.9,
        times_seen=3,
        transcript_indices=[1, 2, 3],
    )
    s = c.to_suggestion_dict()
    assert s["kind"] == "term"
    assert s["canonical"] == "Tavily"
    assert s["aliases_seen"] == ["Tabby"]
    assert "canonical_name" not in s  # term-shape, not speaker-shape


def test_candidate_to_suggestion_dict_for_speaker() -> None:
    c = BootstrapCandidate(
        kind="speaker",
        canonical="Siqi",
        aliases_seen=["司琪"],
        type="person",
        contexts=[],
        confidence=0.8,
        times_seen=1,
        transcript_indices=[1],
    )
    s = c.to_suggestion_dict()
    assert s["kind"] == "speaker"
    assert s["canonical_name"] == "Siqi"
    assert s["display_label"] == "Siqi："
    assert "canonical" not in s

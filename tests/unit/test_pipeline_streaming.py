"""Tests for the streaming pipeline (Pipeline.iter_events).

Covers the contract used by the SSE endpoint and the web UI: that events
arrive in the right order, every chunk_delta carries a non-empty delta and
a running char count, and the final complete event includes a stitched
EditResult.
"""

from __future__ import annotations

import pytest

from clearscript.core.pipeline import Pipeline
from clearscript.ingest.txt import TxtAdapter
from clearscript.providers.base import ChatResponse


class StreamingMockProvider:
    """Provider that yields the canned response in N tiny deltas.

    Lets us verify that pipeline.iter_events forwards every delta and the
    accumulated char count grows monotonically.
    """

    name = "mock-streaming"

    def __init__(self, response_text: str, *, chunks: int = 4) -> None:
        self.response_text = response_text
        self.chunks = chunks

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        return ChatResponse(
            text=self.response_text,
            input_tokens=100,
            output_tokens=50,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        yield self.response_text

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        # Split the response into roughly equal slices so we can assert
        # that multiple delta events flow through.
        n = max(1, self.chunks)
        slice_len = max(1, len(self.response_text) // n)
        for i in range(0, len(self.response_text), slice_len):
            yield ("delta", self.response_text[i : i + slice_len])
        yield (
            "done",
            ChatResponse(
                text=self.response_text,
                input_tokens=100,
                output_tokens=50,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


@pytest.fixture
def short_transcript():
    return TxtAdapter().parse_string("Speaker A: Hello world. This is a short transcript.")


def _make_pipeline(provider, library):
    return Pipeline(
        provider=provider,
        model="mock-model",
        library=library,
    )


def test_event_order_for_single_chunk(tmp_library, short_transcript) -> None:
    """Plan → chunk_start → chunk_delta+ → chunk_done → complete."""
    provider = StreamingMockProvider(
        "Cleaned text.\n\n---CHANGELOG---\n\n---SUGGESTIONS---\n",
        chunks=3,
    )
    pipeline = _make_pipeline(provider, tmp_library)

    events = list(pipeline.iter_events(short_transcript))
    names = [e.name for e in events]

    # Always starts with plan, ends with complete.
    assert names[0] == "plan"
    assert names[-1] == "complete"
    # Exactly one chunk_start for a short transcript.
    assert names.count("chunk_start") == 1
    # Exactly one chunk_done.
    assert names.count("chunk_done") == 1
    # At least one chunk_delta — that's the streaming contract.
    assert names.count("chunk_delta") >= 1
    # No errors.
    assert "error" not in names


def test_chunk_delta_payload_shape(tmp_library, short_transcript) -> None:
    """Every chunk_delta has chunk/total/delta/chars_so_far. chars_so_far grows."""
    provider = StreamingMockProvider(
        "abcdefghij" * 5
        + "\n\n---CHANGELOG---\n\n---SUGGESTIONS---\n",
        chunks=5,
    )
    pipeline = _make_pipeline(provider, tmp_library)

    deltas = [e for e in pipeline.iter_events(short_transcript) if e.name == "chunk_delta"]
    assert len(deltas) >= 2

    last_chars = -1
    for d in deltas:
        for key in ("chunk", "total", "delta", "chars_so_far"):
            assert key in d.data, f"chunk_delta missing {key}"
        # delta must be a non-empty string
        assert isinstance(d.data["delta"], str) and len(d.data["delta"]) > 0
        # chars_so_far must monotonically grow
        assert d.data["chars_so_far"] > last_chars
        last_chars = d.data["chars_so_far"]


def test_complete_carries_stitched_result(tmp_library, short_transcript) -> None:
    provider = StreamingMockProvider(
        "Cleaned output.\n\n---CHANGELOG---\n\n---SUGGESTIONS---\n",
        chunks=2,
    )
    pipeline = _make_pipeline(provider, tmp_library)

    events = list(pipeline.iter_events(short_transcript))
    complete = next(e for e in events if e.name == "complete")
    # The complete event flattens the EditResult so SSE consumers don't
    # need to deserialize a dataclass.
    assert "edited_markdown" in complete.data
    assert "change_log" in complete.data
    assert "suggestions" in complete.data
    assert complete.data["edited_markdown"]


def test_error_during_chunk_terminates_stream(tmp_library, short_transcript) -> None:
    """If the provider raises mid-stream, we get an error event and stop."""

    class ExplodingProvider:
        name = "explody"

        def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        def stream(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise RuntimeError("boom")

        def chat_with_progress(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            yield ("delta", "partial...")
            raise RuntimeError("provider exploded")

    pipeline = _make_pipeline(ExplodingProvider(), tmp_library)
    events = list(pipeline.iter_events(short_transcript))
    names = [e.name for e in events]
    assert "error" in names
    # Once we error out, we don't emit complete.
    assert "complete" not in names


def test_provider_that_never_emits_done_is_an_error(tmp_library, short_transcript) -> None:
    """A misbehaving provider that yields deltas but never 'done' must error."""

    class NoDoneProvider:
        name = "no-done"

        def chat(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            raise NotImplementedError

        def stream(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            yield ""

        def chat_with_progress(self, *args, **kwargs):  # type: ignore[no-untyped-def]
            yield ("delta", "some text")
            # never yields 'done'

    pipeline = _make_pipeline(NoDoneProvider(), tmp_library)
    events = list(pipeline.iter_events(short_transcript))
    assert any(e.name == "error" for e in events)

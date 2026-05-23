"""Tests for the self-review pass (Stage 6).

After all chunks complete, the pipeline runs ONE additional LLM call on
the stitched output to catch missed corrections / inconsistencies /
over-corrections. The pass is opt-out (default ON) — the user
explicitly chose clearscript over ChatGPT for the associative
reasoning, and self-review is where most of that reasoning lands.
"""

from __future__ import annotations

from pathlib import Path

from clearscript.core.pipeline import Pipeline
from clearscript.providers.base import ChatMessage, ChatResponse


class TwoPassProvider:
    """Provider that returns different canned text per call.

    Call 1 is the main edit pass; call 2 is the self-review JSON.
    Lets us simulate the model finding additional corrections.
    """

    name = "two-pass"

    def __init__(
        self,
        edit_response: str,
        review_response: str,
    ) -> None:
        self.edit_response = edit_response
        self.review_response = review_response
        self.calls: list[list[ChatMessage]] = []
        # Track call index separately so the response decision is made
        # BEFORE the append, avoiding off-by-one with len(self.calls).
        self.call_idx = 0

    def _take(self) -> str:
        text = self.edit_response if self.call_idx == 0 else self.review_response
        self.call_idx += 1
        return text

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        return ChatResponse(
            text=self._take(),
            input_tokens=100,
            output_tokens=50,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, *a, **k):  # type: ignore[no-untyped-def]
        yield self._take()

    def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        text = self._take()
        yield ("delta", text)
        yield (
            "done",
            ChatResponse(
                text=text,
                input_tokens=100,
                output_tokens=50,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


def _write_short(path: Path, text: str = "Speaker 1: Tabby is great.\n") -> None:
    path.write_text(text, encoding="utf-8")


# ============ Self-review event ordering ============


def test_iter_events_emits_self_review_events(tmp_path: Path) -> None:
    """When self-review is on, iter_events emits a start + done pair
    between the last chunk_done and the complete event.
    """
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "Speaker A:\n- Tavily is great.\n"
            "---CHANGELOG---\n[{\"layer\":\"L3\",\"old\":\"Tabby\",\"new\":\"Tavily\"}]\n"
            "---SUGGESTIONS---\n[]"
        ),
        review_response='{"additional_corrections":[],"rollbacks":[],"promotions_to_user_review":[],"data_conflicts":[],"format_issues":[]}',
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    transcript = pipeline.run.__wrapped__ if hasattr(pipeline.run, "__wrapped__") else None
    # Use iter_events directly.
    from clearscript.ingest.txt import TxtAdapter
    transcript = TxtAdapter().parse_string(input_path.read_text(encoding="utf-8"))
    events = list(pipeline.iter_events(transcript))
    names = [e.name for e in events]
    assert "self_review_start" in names
    assert "self_review_done" in names
    # Ordering: self_review_start comes after the last chunk_done.
    assert names.index("self_review_start") > names.index("chunk_done")
    assert names.index("self_review_done") < names.index("complete")


def test_self_review_applies_additional_corrections(tmp_path: Path) -> None:
    """The model finds a token the main pass missed; self-review's
    additional_corrections gets applied to the markdown.
    """
    input_path = tmp_path / "t.txt"
    # Main pass leaves 'Minus' in the output; self-review catches it.
    _write_short(input_path, "Speaker 1: We use Minus for agents.\n")

    provider = TwoPassProvider(
        edit_response=(
            "Speaker A:\n- We use Minus for agents.\n"
            "---CHANGELOG---\n[]\n"
            "---SUGGESTIONS---\n[]"
        ),
        review_response=(
            '{"additional_corrections":[{"old":"Minus","new":"Manus",'
            '"reason":"AI agent context","confidence":0.9}],'
            '"rollbacks":[],"promotions_to_user_review":[],'
            '"data_conflicts":[],"format_issues":[]}'
        ),
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    assert "Manus" in result.edited_markdown
    assert "Minus" not in result.edited_markdown
    # The review change shows up in the change log with stage=self_review.
    review_changes = [c for c in result.change_log if c.get("stage") == "self_review"]
    assert len(review_changes) == 1
    assert review_changes[0]["new"] == "Manus"


def test_self_review_token_count_includes_both_passes(tmp_path: Path) -> None:
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "ok\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response='{"additional_corrections":[]}',
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    # Two calls × 100 in + 50 out = 200 in + 100 out.
    assert result.input_tokens == 200
    assert result.output_tokens == 100


# ============ Self-review opt-out ============


def test_self_review_disabled_skips_extra_call(tmp_path: Path) -> None:
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "ok\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response="should not be called",
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=False)
    pipeline.run(input_path)
    # Only the main edit call should have fired.
    assert len(provider.calls) == 1


def test_self_review_skipped_for_huge_output(tmp_path: Path) -> None:
    """Stitched output > self_review_max_chars → review pass auto-skipped
    to keep cost bounded on very long transcripts.
    """
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    huge_text = "X" * 500  # Will produce ~50-byte edited output; cap = 30
    provider = TwoPassProvider(
        edit_response=(
            huge_text + "\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response="should not be called",
    )
    pipeline = Pipeline(
        provider=provider,
        model="m",
        enable_self_review=True,
        self_review_max_chars=30,  # smaller than the edit output
    )
    pipeline.run(input_path)
    assert len(provider.calls) == 1


# ============ Self-review robustness ============


def test_self_review_garbage_response_doesnt_crash(tmp_path: Path) -> None:
    """If the model returns unparseable garbage to the self-review call,
    we skip applying corrections but the main result still ships.
    """
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "edited content here\n"
            "---CHANGELOG---\n[]\n"
            "---SUGGESTIONS---\n[]"
        ),
        review_response="this is not JSON at all {",
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    # Main result survives even though review JSON was bad.
    assert "edited content here" in result.edited_markdown
    # No additional changes applied.
    assert all(c.get("stage") != "self_review" for c in result.change_log)


def test_self_review_diagnostics_surfaced_in_complete(tmp_path: Path) -> None:
    """The 'complete' event carries self_review diagnostics so the UI can
    show data conflicts + promoted-to-user-review items.
    """
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "ok\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response=(
            '{"additional_corrections":[],'
            '"rollbacks":[],"promotions_to_user_review":['
            '{"location":"para 1","issue":"ambiguous","options":["A","B"]}],'
            '"data_conflicts":[{"locations":["x","y"],"metric":"ARR","values":["$1M","$1.5M"]}],'
            '"format_issues":[]}'
        ),
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    from clearscript.ingest.txt import TxtAdapter
    transcript = TxtAdapter().parse_string(input_path.read_text(encoding="utf-8"))
    complete_event = None
    for event in pipeline.iter_events(transcript):
        if event.name == "complete":
            complete_event = event
    assert complete_event is not None
    review = complete_event.data["self_review"]
    assert review is not None
    assert len(review["promotions_to_user_review"]) == 1
    assert len(review["data_conflicts"]) == 1
    assert review["data_conflicts"][0]["metric"] == "ARR"


def test_self_review_ignores_corrections_where_old_not_in_doc(tmp_path: Path) -> None:
    """Model hallucinates a correction whose ``old`` doesn't appear in
    the edited markdown — silently ignore (don't apply).
    """
    input_path = tmp_path / "t.txt"
    _write_short(input_path)

    provider = TwoPassProvider(
        edit_response=(
            "Speaker A: real output\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response=(
            '{"additional_corrections":[{"old":"DoesNotExist","new":"X","reason":"oops"}],'
            '"rollbacks":[],"promotions_to_user_review":[],"data_conflicts":[],"format_issues":[]}'
        ),
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    assert "real output" in result.edited_markdown
    assert "X" not in result.edited_markdown
    # No change applied because 'DoesNotExist' wasn't in the doc.
    review_changes = [c for c in result.change_log if c.get("stage") == "self_review"]
    assert review_changes == []

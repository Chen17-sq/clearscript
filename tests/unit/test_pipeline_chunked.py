"""Tests for the multi-chunk pipeline path."""

from __future__ import annotations

from pathlib import Path

from clearscript.core.pipeline import Pipeline

# Each chunk's mock output. We rotate through these so the mock provider
# returns plausibly different content per call.
CHUNK_OUTPUT_TEMPLATE = """Speaker 1：
- Chunk {n} body line one.
- Chunk {n} body line two.

---CHANGELOG---
[{{"layer": "L3", "old": "OLD{n}", "new": "NEW{n}", "reason": "test"}}]

---SUGGESTIONS---
[{{"kind": "term", "canonical": "Term{n}", "type": "company", "aliases_seen": ["Alias{n}"]}}]
"""


class RotatingMockProvider:
    """Mock provider that returns a different fake response per call."""

    name = "rotating-mock"

    def __init__(self) -> None:
        self.call_count = 0

    def chat(self, messages, model, **kwargs):
        from clearscript.providers.base import ChatResponse

        self.call_count += 1
        text = CHUNK_OUTPUT_TEMPLATE.format(n=self.call_count)
        return ChatResponse(
            text=text,
            input_tokens=100,
            output_tokens=80,
            model=model,
            provider=self.name,
            latency_ms=1.0,
        )

    def stream(self, messages, model, **kwargs):
        yield ""

    def chat_with_progress(self, messages, model, **kwargs):
        from clearscript.providers.base import ChatResponse

        self.call_count += 1
        text = CHUNK_OUTPUT_TEMPLATE.format(n=self.call_count)
        yield ("delta", text)
        yield (
            "done",
            ChatResponse(
                text=text,
                input_tokens=100,
                output_tokens=80,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


def _write_long_transcript(path: Path, num_turns: int = 200, chars_per_turn: int = 250) -> None:
    """Write a synthetic transcript long enough to trigger chunking."""
    lines = []
    payload = "X" * chars_per_turn
    for i in range(num_turns):
        speaker = "Speaker 1" if i % 2 == 0 else "Speaker 2"
        lines.append(f"{speaker}: {payload}")
    path.write_text("\n".join(lines), encoding="utf-8")


def test_long_transcript_triggers_multi_chunk(tmp_path: Path) -> None:
    input_path = tmp_path / "long.txt"
    _write_long_transcript(input_path)

    provider = RotatingMockProvider()
    # Self-review adds an extra LLM call after all chunks; disable here so
    # the chunk-count assertions stay clean. Self-review is exercised in
    # its own test module.
    pipeline = Pipeline(provider=provider, model="mock-1", enable_self_review=False)
    result = pipeline.run(input_path)

    # Should have made multiple LLM calls
    assert provider.call_count > 1
    assert result.num_chunks == provider.call_count
    # Stitched markdown should contain content from each chunk
    for n in range(1, provider.call_count + 1):
        assert f"Chunk {n}" in result.edited_markdown
    # All chunks' change logs should be merged
    assert len(result.change_log) == provider.call_count
    # Each change should be tagged with its chunk index
    for change in result.change_log:
        assert "chunk" in change


def test_short_transcript_stays_single_chunk(tmp_path: Path) -> None:
    input_path = tmp_path / "short.txt"
    input_path.write_text("Speaker 1: hi.\nSpeaker 2: hello.", encoding="utf-8")

    provider = RotatingMockProvider()
    pipeline = Pipeline(provider=provider, model="mock-1", enable_self_review=False)
    result = pipeline.run(input_path)

    assert provider.call_count == 1
    assert result.num_chunks == 1


def test_suggestions_dedup_across_chunks(tmp_path: Path) -> None:
    """Same canonical proposed by multiple chunks → only one entry in result."""

    class DupSuggestProvider:
        name = "dup-mock"

        def chat(self, messages, model, **kwargs):
            from clearscript.providers.base import ChatResponse

            payload = (
                "Speaker 1：\n- some body\n"
                "---CHANGELOG---\n[]\n"
                "---SUGGESTIONS---\n"
                '[{"kind": "term", "canonical": "Dify", "aliases_seen": ["DeFi"]}]'
            )
            return ChatResponse(
                text=payload,
                input_tokens=50,
                output_tokens=30,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            )

        def stream(self, messages, model, **kwargs):
            yield ""

        def chat_with_progress(self, messages, model, **kwargs):
            from clearscript.providers.base import ChatResponse

            payload = (
                "Speaker 1：\n- some body\n"
                "---CHANGELOG---\n[]\n"
                "---SUGGESTIONS---\n"
                '[{"kind": "term", "canonical": "Dify", "aliases_seen": ["DeFi"]}]'
            )
            yield ("delta", payload)
            yield (
                "done",
                ChatResponse(
                    text=payload,
                    input_tokens=50,
                    output_tokens=30,
                    model=model,
                    provider=self.name,
                    latency_ms=1.0,
                ),
            )

    input_path = tmp_path / "long.txt"
    _write_long_transcript(input_path)
    provider = DupSuggestProvider()
    pipeline = Pipeline(provider=provider, model="mock-1")
    result = pipeline.run(input_path)

    assert result.num_chunks > 1
    # Only one "Dify" suggestion should survive deduplication
    canonicals = [s.get("canonical") for s in result.suggestions]
    assert canonicals.count("Dify") == 1


def test_token_counts_are_summed_across_chunks(tmp_path: Path) -> None:
    input_path = tmp_path / "long.txt"
    _write_long_transcript(input_path)

    provider = RotatingMockProvider()
    pipeline = Pipeline(provider=provider, model="mock-1")
    result = pipeline.run(input_path)

    # Each call returns input_tokens=100, output_tokens=80
    assert result.input_tokens == 100 * provider.call_count
    assert result.output_tokens == 80 * provider.call_count
    assert result.total_tokens == 180 * provider.call_count

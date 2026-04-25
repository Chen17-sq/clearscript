"""Tests for the v0.0.1 pipeline using the mock provider."""

from __future__ import annotations

from pathlib import Path

from clearscript.core.pipeline import Pipeline

MOCK_OUTPUT = """Speaker 1：
- Hi everyone, can you hear me?

Speaker 2：
- Yes I can.

---CHANGELOG---
[
  {"layer": "L1", "old": "Speaker 1:", "new": "Speaker 1：", "reason": "punctuation normalization", "confidence": 1.0}
]
"""


def test_pipeline_runs_end_to_end(tmp_path: Path, mock_provider) -> None:
    mock_provider.response_text = MOCK_OUTPUT
    input_path = tmp_path / "transcript.txt"
    input_path.write_text(
        "Speaker 1: Hi everyone, can you hear me?\nSpeaker 2: Yes I can.\n",
        encoding="utf-8",
    )

    pipeline = Pipeline(provider=mock_provider, model="mock-model")
    result = pipeline.run(input_path)

    assert "Speaker 1：" in result.edited_markdown
    assert "Hi everyone" in result.edited_markdown
    assert len(result.change_log) == 1
    assert result.change_log[0]["layer"] == "L1"
    assert result.input_tokens == 100
    assert result.output_tokens == 50


def test_pipeline_handles_no_changelog(tmp_path: Path, mock_provider) -> None:
    mock_provider.response_text = "Just markdown, no changelog."
    input_path = tmp_path / "transcript.txt"
    input_path.write_text("Speaker 1: Hi.\n", encoding="utf-8")
    pipeline = Pipeline(provider=mock_provider, model="mock-model")
    result = pipeline.run(input_path)
    assert "Just markdown" in result.edited_markdown
    assert result.change_log == []


def test_pipeline_uses_library_speaker_mapping(tmp_path: Path, mock_provider, tmp_library) -> None:
    tmp_library.add_speaker(
        canonical_name="Eileen", display_label="Eileen：", aliases=["Speaker 2"]
    )
    mock_provider.response_text = "Output\n---CHANGELOG---\n[]"

    input_path = tmp_path / "transcript.txt"
    input_path.write_text("Speaker 2: Hi.\n", encoding="utf-8")
    pipeline = Pipeline(provider=mock_provider, model="mock-model", library=tmp_library)
    pipeline.run(input_path)

    system_msg = mock_provider.calls[0][0]
    assert "Speaker 2" in system_msg.content
    assert "Eileen" in system_msg.content

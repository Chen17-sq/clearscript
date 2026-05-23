"""Tests for the pipeline using the mock provider."""

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

---SUGGESTIONS---
[
  {"kind": "term", "canonical": "PingCAP", "type": "company", "domain": "ai-infra", "aliases_seen": ["PinkCup"]},
  {"kind": "speaker", "canonical_name": "Eileen", "display_label": "Eileen：", "aliases_seen": ["Speaker 2"]}
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


def test_pipeline_parses_suggestions(tmp_path: Path, mock_provider) -> None:
    """Mode B: SUGGESTIONS block is parsed into EditResult.suggestions."""
    mock_provider.response_text = MOCK_OUTPUT
    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: Hi.\n", encoding="utf-8")
    pipeline = Pipeline(provider=mock_provider, model="mock-model")
    result = pipeline.run(input_path)

    assert len(result.suggestions) == 2
    kinds = sorted(s["kind"] for s in result.suggestions)
    assert kinds == ["speaker", "term"]
    term = next(s for s in result.suggestions if s["kind"] == "term")
    assert term["canonical"] == "PingCAP"
    assert "PinkCup" in term["aliases_seen"]


def test_pipeline_empty_suggestions(tmp_path: Path, mock_provider) -> None:
    mock_provider.response_text = "Output\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: Hi.\n", encoding="utf-8")
    pipeline = Pipeline(provider=mock_provider, model="mock-model")
    result = pipeline.run(input_path)
    assert result.suggestions == []


def test_pipeline_extract_entities() -> None:
    """Mode A: briefing entity extraction picks up CamelCase, acronyms, and CJK names."""
    text = (
        "Speaker 1 = Siqi (host); Speaker 2 = Eileen (founder of Acme); "
        "seed terms: Dify, Manus, Mem9, MAM-9, PMF, 张三, 君晨"
    )
    entities = Pipeline._extract_entities(text)
    for token in ("Siqi", "Eileen", "Acme", "Dify", "Manus", "Mem9", "PMF", "张三", "君晨"):
        assert token in entities, f"missing: {token}"


def test_pipeline_briefing_seeds_pulled_into_context(
    tmp_path: Path, mock_provider, tmp_library
) -> None:
    """Mode A end-to-end: term in briefing gets looked up and added to system prompt."""
    tmp_library.add_term(canonical="Dify", aliases=["DeFi"], type_="company", domain="ai-infra")
    mock_provider.response_text = "Output\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"

    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: hello.\n", encoding="utf-8")
    pipeline = Pipeline(
        provider=mock_provider,
        model="mock-model",
        library=tmp_library,
        briefing_context="Speaker 1 = host; companies discussed: Dify, Manus",
    )
    pipeline.run(input_path)

    system_msg = mock_provider.calls[0][0]
    assert "Term mappings from your library" in system_msg.content
    assert "Dify" in system_msg.content


def test_pipeline_transcript_seeds_pulled_into_context_without_briefing(
    tmp_path: Path, mock_provider, tmp_library
) -> None:
    """Regression: a library alias appearing only in the transcript (no briefing)
    must still surface in the system prompt.

    Before v0.0.11, ``_collect_library_context`` only scanned the briefing,
    so a user with no briefing got an empty library context — the seed pack
    was effectively dead weight. This is the bug behind the user's
    "Tabby is not getting fixed to Tavily" complaint.
    """
    tmp_library.add_term(canonical="Tavily", aliases=["Tabby"], type_="company")
    mock_provider.response_text = "Output\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"

    input_path = tmp_path / "t.txt"
    input_path.write_text(
        "Speaker 1: We use Tabby for search.\nSpeaker 2: Yeah, Tabby is great.\n",
        encoding="utf-8",
    )
    pipeline = Pipeline(
        provider=mock_provider,
        model="mock-model",
        library=tmp_library,
        briefing_context="",  # explicitly no briefing
    )
    pipeline.run(input_path)

    system_msg = mock_provider.calls[0][0]
    assert "Term mappings from your library" in system_msg.content
    assert "Tabby" in system_msg.content
    assert "Tavily" in system_msg.content


def test_pipeline_mode_c_propagates_substitutions_across_chunks(
    tmp_path: Path, tmp_library
) -> None:
    """Mode C: a substitution committed in chunk 1 shows up in chunk 2's prompt."""
    from clearscript.providers.base import ChatResponse

    class TwoChunkProvider:
        name = "twochunk"

        def __init__(self) -> None:
            self.calls: list[list] = []
            self.responses = [
                # Chunk 1: model "discovers" Tabby → Tavily
                "Speaker 1: We use Tavily for search.\n"
                "---CHANGELOG---\n"
                '[{"layer": "L3", "before": "Tabby", "after": "Tavily", "reason": "company name"}]\n'
                "---SUGGESTIONS---\n[]",
                # Chunk 2: trivial output, no new changes
                "Speaker 2: More content.\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]",
            ]

        def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            idx = len(self.calls)
            self.calls.append(list(messages))
            text = self.responses[idx] if idx < len(self.responses) else self.responses[-1]
            return ChatResponse(
                text=text,
                input_tokens=100,
                output_tokens=50,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            )

        def stream(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            yield self.chat(messages, model, **kwargs).text

        def chat_with_progress(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
            resp = self.chat(messages, model, **kwargs)
            yield ("delta", resp.text)
            yield ("done", resp)

    provider = TwoChunkProvider()
    pipeline = Pipeline(
        provider=provider,
        model="mock-model",
        library=tmp_library,
        # Force two chunks by setting tiny target tokens.
        chunk_target_tokens=20,
        chunk_trigger_tokens=20,
        chunk_hard_max_tokens=100,
    )
    # Make sure plan returns two chunks.
    long_text = "Speaker 1: " + ("word " * 50) + "\nSpeaker 2: " + ("more " * 50) + "\n"
    input_path = tmp_path / "t.txt"
    input_path.write_text(long_text, encoding="utf-8")
    pipeline.run(input_path)

    assert len(provider.calls) >= 2, "expected the transcript to be chunked"
    # Chunk 2's system prompt should mention the Tabby → Tavily decision.
    chunk2_system = provider.calls[1][0].content
    assert "Earlier chunks in this same run" in chunk2_system
    assert "Tabby" in chunk2_system
    assert "Tavily" in chunk2_system


def test_pipeline_split_output_returns_raw_when_no_delimiters() -> None:
    """If the model ignores the format instructions, we must still extract
    the cleaned text without crashing — empty changelog/suggestions is
    better than a 500.
    """
    edited, changelog, suggestions = Pipeline._split_output("just some text\nno delimiters")
    assert edited == "just some text\nno delimiters"
    assert changelog == []
    assert suggestions == []


def test_pipeline_split_output_handles_malformed_json_changelog() -> None:
    """JSON parse failure in the changelog section must not propagate."""
    text = (
        "Cleaned\n"
        "---CHANGELOG---\n"
        "{this is not valid json\n"
        "---SUGGESTIONS---\n"
        "[]"
    )
    edited, changelog, suggestions = Pipeline._split_output(text)
    assert edited == "Cleaned"
    assert changelog == []
    assert suggestions == []


def test_pipeline_split_output_filters_non_dict_entries() -> None:
    """LLMs occasionally yield arrays of strings — filter them out."""
    text = (
        "Cleaned\n"
        "---CHANGELOG---\n"
        '["not a dict", {"layer": "L3"}, 42]\n'
        "---SUGGESTIONS---\n"
        "[]"
    )
    _edited, changelog, _ = Pipeline._split_output(text)
    assert len(changelog) == 1
    assert changelog[0]["layer"] == "L3"


def test_dedupe_suggestions_merges_by_canonical() -> None:
    from clearscript.core.pipeline import _dedupe_suggestions

    items = [
        {"kind": "term", "canonical": "Dify"},
        {"kind": "term", "canonical": "Dify"},  # exact dup
        {"kind": "term", "canonical": "DIFY"},  # case dup
        {"kind": "term", "canonical": "Manus"},
        {"kind": "speaker", "canonical_name": "Eileen"},
    ]
    out = _dedupe_suggestions(items)
    assert len(out) == 3  # Dify (once) + Manus + Eileen


def test_dedupe_suggestions_skips_items_with_no_identity() -> None:
    from clearscript.core.pipeline import _dedupe_suggestions

    items = [
        {"kind": "term"},  # no canonical/title
        {"kind": "term", "canonical": "Dify"},
        {},
    ]
    out = _dedupe_suggestions(items)
    assert len(out) == 1
    assert out[0]["canonical"] == "Dify"


def test_pipeline_split_output_handles_no_suggestions_section(mock_provider) -> None:
    text = "Edited text\n---CHANGELOG---\n[]"
    edited, changelog, suggestions = Pipeline._split_output(text)
    assert edited == "Edited text"
    assert changelog == []
    assert suggestions == []


def test_pipeline_split_output_handles_fenced_json(mock_provider) -> None:
    text = (
        "Edited\n"
        "---CHANGELOG---\n"
        '```json\n[{"layer": "L1", "old": "a", "new": "b"}]\n```\n'
        "---SUGGESTIONS---\n"
        '```json\n[{"kind": "term", "canonical": "X"}]\n```\n'
    )
    _edited, changelog, suggestions = Pipeline._split_output(text)
    assert len(changelog) == 1
    assert len(suggestions) == 1
    assert suggestions[0]["canonical"] == "X"

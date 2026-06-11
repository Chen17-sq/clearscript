"""Regression tests for the v0.0.21 audit fixes.

Each test pins one confirmed finding from the 61-agent deep audit so the
bug class can't silently return. Names reference the finding.
"""

from __future__ import annotations

from pathlib import Path

from clearscript.core.pipeline import Pipeline
from clearscript.ingest.txt import TxtAdapter
from clearscript.providers.base import ChatMessage, ChatResponse
from clearscript.storage import ProjectStore

# ============ library/manager.py ============


def test_search_terms_survives_fts5_syntax_input(tmp_library) -> None:
    """FTS5 used to raise OperationalError on query-syntax input —
    `a AND`, unbalanced quotes, trailing hyphens."""
    tmp_library.add_term(canonical="Tavily", aliases=["Tabby"])
    for nasty in ['a AND', '"unclosed', "term-", "NOT", "(paren", "*star"]:
        # Must not raise; result content is secondary.
        tmp_library.search_terms(nasty)
    # Sane queries still hit.
    hits = tmp_library.search_terms("Tavily")
    assert any(h.canonical == "Tavily" for h in hits)


def test_export_import_preserves_status_and_definition(tmp_library, tmp_path) -> None:
    """Round-trip used to demote confirmed/verified terms back to
    'proposed' and drop definition/notes."""
    from clearscript.library import Library

    term_id = tmp_library.add_term(
        canonical="Dify",
        aliases=["DeFi"],
        type_="company",
        definition="LLM app platform",
    )
    for _ in range(3):
        tmp_library.confirm_term(term_id)  # → verified
    payload = tmp_library.export_dict()

    target = Library(tmp_path / "target.db")
    try:
        target.import_dict(payload)
        rows = target.list_terms(search="Dify")
        assert rows, "imported term not found"
        imported = rows[0]
        assert imported["status"] == "verified"
        assert imported["definition"] == "LLM app platform"
    finally:
        target.close()


def test_all_terms_in_domain_excludes_deprecated_universal(tmp_library) -> None:
    """Operator precedence: deprecated NULL-domain terms leaked through
    `domain IS NULL OR domain = ? AND status != 'deprecated'`."""
    keep = tmp_library.add_term(canonical="Keep")  # NULL domain
    drop = tmp_library.add_term(canonical="Drop")  # NULL domain
    tmp_library.reject_term(drop)
    assert keep != drop
    hits = tmp_library.all_terms_in_domain("vc")
    canonicals = {h.canonical for h in hits}
    assert "Keep" in canonicals
    assert "Drop" not in canonicals


def test_import_rejects_wrong_shaped_collections(tmp_library) -> None:
    """A terms value that isn't a list used to crash mid-merge (500 with
    partial commit). Now it's a clean ValueError before any write."""
    import pytest

    with pytest.raises(ValueError, match="must be a list"):
        tmp_library.import_dict(
            {
                "format": "clearscript-library-export",
                "schema_version": 1,
                "terms": {"canonical": "not-a-list"},
            }
        )


def test_import_skips_non_dict_entries(tmp_library) -> None:
    summary = tmp_library.import_dict(
        {
            "format": "clearscript-library-export",
            "schema_version": 1,
            "terms": ["just-a-string", {"canonical": "Real"}],
            "speakers": [42],
            "edit_patterns": [None],
            "negatives": [],
        }
    )
    assert summary["terms_added"] == 1
    assert summary["skipped"] == 3


# ============ storage/filesystem.py ============


def test_corrupted_meta_json_does_not_brick_listing(tmp_path: Path) -> None:
    """One truncated meta.json used to crash list_summaries (and with it
    /api/projects, the inbox, compare...)."""
    store = ProjectStore(tmp_path)
    good = store.create("good project")
    good.save_run(
        title="ok",
        format_="txt",
        provider="m",
        model="m",
        input_text="hi",
        edited_markdown="done",
        change_log=[],
        suggestions=[],
        input_tokens=1,
        output_tokens=1,
    )
    bad = store.create("bad project")
    bad.save_run(
        title="bad",
        format_="txt",
        provider="m",
        model="m",
        input_text="hi",
        edited_markdown="done",
        change_log=[],
        suggestions=[],
        input_tokens=1,
        output_tokens=1,
    )
    # Corrupt the second project's meta mid-write style.
    bad.meta_path.write_text('{"slug": "trunca', encoding="utf-8")

    summaries = store.list_summaries()
    slugs = [s["slug"] for s in summaries]
    assert good.slug in slugs
    # The corrupted project still appears (slug known from dir name).
    assert bad.slug in slugs


def test_write_meta_is_atomic_no_tmp_residue(tmp_path: Path) -> None:
    store = ProjectStore(tmp_path)
    p = store.create("atomic")
    p.ensure_dirs()
    p.write_meta({"slug": p.slug, "title": "x"})
    assert p.read_meta()["title"] == "x"
    # No temp file left behind.
    leftovers = list(p.root.glob("*.tmp"))
    assert leftovers == []


# ============ pipeline self-review guards ============


class TwoPassProvider:
    name = "two-pass"

    def __init__(self, edit_response: str, review_response: str) -> None:
        self.edit_response = edit_response
        self.review_response = review_response
        self.call_idx = 0
        self.calls: list[list[ChatMessage]] = []

    def _take(self) -> str:
        text = self.edit_response if self.call_idx == 0 else self.review_response
        self.call_idx += 1
        return text

    def chat(self, messages, model, **kwargs):  # type: ignore[no-untyped-def]
        self.calls.append(list(messages))
        return ChatResponse(
            text=self._take(),
            input_tokens=10,
            output_tokens=5,
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
                input_tokens=10,
                output_tokens=5,
                model=model,
                provider=self.name,
                latency_ms=1.0,
            ),
        )


def test_self_review_skips_multi_occurrence_old(tmp_path: Path) -> None:
    """`replace(old, new, 1)` on an ambiguous needle could hit the wrong
    occurrence — those corrections now route to user review instead."""
    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: x\n", encoding="utf-8")
    provider = TwoPassProvider(
        edit_response=(
            "alpha beta alpha\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response=(
            '{"additional_corrections":[{"old":"alpha","new":"gamma","reason":"x"}],'
            '"rollbacks":[],"promotions_to_user_review":[],"data_conflicts":[],"format_issues":[]}'
        ),
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    # NOT applied — 'alpha' appears twice.
    assert "gamma" not in result.edited_markdown
    assert result.edited_markdown.count("alpha") == 2


def test_self_review_skips_empty_new(tmp_path: Path) -> None:
    """A correction with empty 'new' used to silently delete text."""
    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: x\n", encoding="utf-8")
    provider = TwoPassProvider(
        edit_response=(
            "keep this sentence intact\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]"
        ),
        review_response=(
            '{"additional_corrections":[{"old":"this sentence","new":"","reason":"?"}],'
            '"rollbacks":[],"promotions_to_user_review":[],"data_conflicts":[],"format_issues":[]}'
        ),
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    result = pipeline.run(input_path)
    assert "this sentence" in result.edited_markdown


def test_self_review_payload_is_plain_sections_not_nested_json(tmp_path: Path) -> None:
    """The review user message used to double-wrap the whole transcript in
    a JSON string — now it's plain sections with markers."""
    input_path = tmp_path / "t.txt"
    input_path.write_text("Speaker 1: marker test\n", encoding="utf-8")
    provider = TwoPassProvider(
        edit_response="cleaned output\n---CHANGELOG---\n[]\n---SUGGESTIONS---\n[]",
        review_response='{"additional_corrections":[]}',
    )
    pipeline = Pipeline(provider=provider, model="m", enable_self_review=True)
    pipeline.run(input_path)
    review_msg = provider.calls[1][1].content
    assert "<<<TRANSCRIPT_START>>>" in review_msg
    assert "cleaned output" in review_msg
    # Not JSON-escaped (the old payload would have had \"cleaned output\").
    assert '\\"cleaned output\\"' not in review_msg


# ============ chunk-position note (L2 content-loss fix) ============


def test_user_prompt_carries_chunk_position_for_multichunk(tmp_library) -> None:
    pipeline = Pipeline(provider=None, model="m", library=None)  # type: ignore[arg-type]
    chunk = TxtAdapter().parse_string("Speaker 1: hello\n")

    first = pipeline._build_user_prompt(chunk, chunk_index=1, chunk_total=3)
    middle = pipeline._build_user_prompt(chunk, chunk_index=2, chunk_total=3)
    last = pipeline._build_user_prompt(chunk, chunk_index=3, chunk_total=3)
    single = pipeline._build_user_prompt(chunk, chunk_index=1, chunk_total=1)

    assert "FIRST chunk" in first
    assert "MIDDLE chunk" in middle
    assert "does NOT apply" in middle
    assert "LAST chunk" in last
    # Single-chunk runs carry no position note at all.
    assert "Chunk position" not in single


# ============ slug: filenames bypass pleasantry heuristics ============


def test_chinese_filename_stem_used_as_slug() -> None:
    from clearscript.api.slugs import _slug_hint_from_input

    hint = _slug_hint_from_input(
        "Speaker 1: 测一下麦",
        "好的会议记录.docx",  # starts with 好的 — used to be rejected
    )
    assert hint == "好的会议记录"

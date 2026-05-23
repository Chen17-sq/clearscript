"""Tests for the SQLite library."""

from __future__ import annotations


def test_add_and_lookup_term(tmp_library) -> None:
    term_id = tmp_library.add_term(
        canonical="Dify",
        aliases=["DeFi", "底牌", "Difan"],
        type_="company",
        domain="ai-infra",
    )
    assert term_id > 0

    hit = tmp_library.lookup_alias("DeFi")
    assert hit is not None
    assert hit.canonical == "Dify"
    assert hit.domain == "ai-infra"


def test_add_existing_term_appends_aliases(tmp_library) -> None:
    tmp_library.add_term(canonical="Mem9", aliases=["MAM-9"])
    tmp_library.add_term(canonical="Mem9", aliases=["Mam9", "妈姆9"])

    for alias in ("MAM-9", "Mam9", "妈姆9"):
        hit = tmp_library.lookup_alias(alias)
        assert hit is not None
        assert hit.canonical == "Mem9"


def test_confirm_promotes_status(tmp_library) -> None:
    term_id = tmp_library.add_term(canonical="Manus", aliases=["Minus"])
    for _ in range(3):
        tmp_library.confirm_term(term_id)
    hit = tmp_library.lookup_alias("Minus")
    assert hit is not None
    assert hit.confidence > 0.5


def test_speaker_lookup(tmp_library) -> None:
    tmp_library.add_speaker(
        canonical_name="Eileen",
        display_label="Eileen：",
        aliases=["阿丽", "安丽", "艾迪"],
    )
    hit = tmp_library.lookup_speaker("阿丽")
    assert hit is not None
    assert hit.canonical_name == "Eileen"
    assert hit.display_label == "Eileen："


def test_lookup_miss_returns_none(tmp_library) -> None:
    assert tmp_library.lookup_alias("nonexistent") is None
    assert tmp_library.lookup_speaker("nobody") is None


def test_stats(tmp_library) -> None:
    tmp_library.add_term(canonical="A", aliases=["a"])
    tmp_library.add_term(canonical="B", aliases=["b"])
    tmp_library.add_speaker(canonical_name="Person", display_label="Person:")
    stats = tmp_library.stats()
    assert stats["terms"] == 2
    assert stats["speakers"] == 1


def test_session_lifecycle(tmp_library) -> None:
    sid = tmp_library.start_session(project_slug="test", provider="mock", model="mock-1")
    assert sid > 0
    tmp_library.finish_session(sid, input_tokens=100, output_tokens=50)
    stats = tmp_library.stats()
    assert stats["sessions"] == 1


# ============ Listing / filtering ============


def test_list_terms_returns_aliases(tmp_library) -> None:
    tmp_library.add_term(
        canonical="Dify", aliases=["DeFi", "底牌"], type_="company", domain="ai-infra"
    )
    tmp_library.add_term(canonical="Manus", aliases=["Minus"], type_="company", domain="ai-infra")
    tmp_library.add_term(canonical="Mem9", aliases=["MAM-9"], type_="product")

    terms = tmp_library.list_terms()
    assert len(terms) == 3
    dify = next(t for t in terms if t["canonical"] == "Dify")
    assert sorted(dify["aliases"]) == ["DeFi", "底牌"]
    assert dify["type"] == "company"
    assert dify["domain"] == "ai-infra"


def test_list_terms_filter_by_type(tmp_library) -> None:
    tmp_library.add_term(canonical="Dify", type_="company")
    tmp_library.add_term(canonical="Mem9", type_="product")
    only_companies = tmp_library.list_terms(type_="company")
    assert len(only_companies) == 1
    assert only_companies[0]["canonical"] == "Dify"


def test_list_terms_filter_by_status(tmp_library) -> None:
    tid = tmp_library.add_term(canonical="Dify", aliases=["DeFi"])
    tmp_library.confirm_term(tid)
    proposed = tmp_library.list_terms(status="proposed")
    confirmed = tmp_library.list_terms(status="confirmed")
    assert len(proposed) == 0
    assert len(confirmed) == 1


def test_list_terms_search_alias(tmp_library) -> None:
    tmp_library.add_term(canonical="Dify", aliases=["DeFi"])
    tmp_library.add_term(canonical="Manus", aliases=["Minus"])
    hits = tmp_library.list_terms(search="DeFi")
    assert len(hits) == 1
    assert hits[0]["canonical"] == "Dify"


def test_update_term(tmp_library) -> None:
    tid = tmp_library.add_term(canonical="Dify", aliases=["DeFi"])
    tmp_library.update_term(tid, canonical="Dify-AI", domain="ai-infra", aliases=["DeFi", "Difan"])
    terms = tmp_library.list_terms()
    assert terms[0]["canonical"] == "Dify-AI"
    assert sorted(terms[0]["aliases"]) == ["DeFi", "Difan"]
    assert terms[0]["domain"] == "ai-infra"


def test_delete_term(tmp_library) -> None:
    tid = tmp_library.add_term(canonical="Dify")
    tmp_library.delete_term(tid)
    assert tmp_library.list_terms() == []


# ============ Speakers / patterns / negatives ============


def test_list_speakers(tmp_library) -> None:
    tmp_library.add_speaker(
        canonical_name="Eileen", display_label="Eileen：", aliases=["阿丽", "安丽"]
    )
    speakers = tmp_library.list_speakers()
    assert len(speakers) == 1
    assert sorted(speakers[0]["aliases"]) == ["alphabet-fix"][:0] + sorted(["阿丽", "安丽"])


def test_speakers_search(tmp_library) -> None:
    tmp_library.add_speaker(canonical_name="Eileen", display_label="Eileen：", aliases=["阿丽"])
    tmp_library.add_speaker(canonical_name="John", display_label="John:")
    hits = tmp_library.list_speakers(search="阿丽")
    assert len(hits) == 1
    assert hits[0]["canonical_name"] == "Eileen"


def test_edit_pattern_lifecycle(tmp_library) -> None:
    pid = tmp_library.add_edit_pattern(
        title="Preserve approximate numbers",
        trigger_desc="When speaker says ranges like '差不多三四百人'",
        action="Keep original phrasing, do not standardize",
        rationale="Preserves speaker uncertainty signal",
        domain="vc",
    )
    assert pid > 0
    patterns = tmp_library.list_edit_patterns()
    assert len(patterns) == 1
    assert patterns[0]["title"] == "Preserve approximate numbers"

    tmp_library.delete_edit_pattern(pid)
    assert tmp_library.list_edit_patterns() == []


def test_negatives(tmp_library) -> None:
    tmp_library.add_negative(
        text="蛮好的", do_not_change_to="很好", reason="Preserves speaker style"
    )
    tmp_library.add_negative(
        text="蛮好的", do_not_change_to="很好", reason="Duplicate"
    )  # idempotent
    negatives = tmp_library.list_negatives()
    assert len(negatives) == 1


def test_stats_includes_new_categories(tmp_library) -> None:
    tmp_library.add_term(canonical="A")
    tmp_library.add_speaker(canonical_name="Bob", display_label="Bob:")
    tmp_library.add_edit_pattern(title="X", trigger_desc="t", action="a")
    tmp_library.add_negative(text="x")
    stats = tmp_library.stats()
    assert stats["terms"] == 1
    assert stats["proposed_terms"] == 1
    assert stats["edit_patterns"] == 1
    assert stats["negative_rules"] == 1


# ============ Edge cases & robustness ============


def test_lookup_alias_finds_canonical_directly(tmp_library) -> None:
    """The seed pack stores 'Dify' as canonical with 'DeFi' as alias.
    Asking for 'Dify' directly (not via alias) must also resolve, because
    the pipeline's entity extractor may surface either form.
    """
    tmp_library.add_term(canonical="Dify", aliases=["DeFi"])
    by_canonical = tmp_library.lookup_alias("Dify")
    assert by_canonical is not None
    assert by_canonical.canonical == "Dify"


def test_add_term_with_empty_aliases_still_creates_canonical(tmp_library) -> None:
    """A term without any aliases is still a valid library entry — Mode B
    sometimes accepts terms before the user has seen real ASR misspellings.
    """
    term_id = tmp_library.add_term(canonical="SoloCanonical", aliases=[])
    assert term_id > 0
    hit = tmp_library.lookup_alias("SoloCanonical")
    assert hit is not None


def test_search_terms_fts_finds_partial_match(tmp_library) -> None:
    """FTS5 lets users find a term by typing part of the canonical name."""
    tmp_library.add_term(canonical="Anthropic", aliases=["iShopee"])
    tmp_library.add_term(canonical="OpenAI", aliases=["O AI"])
    results = tmp_library.search_terms("Anthropic")
    canonicals = {h.canonical for h in results}
    assert "Anthropic" in canonicals


def test_reject_term_marks_as_deprecated(tmp_library) -> None:
    """Mode B: when the user rejects a suggestion, the term shouldn't
    silently resurface in subsequent prompt contexts.
    """
    term_id = tmp_library.add_term(canonical="Junk", aliases=["jnk"])
    tmp_library.reject_term(term_id)
    # all_terms_in_domain filters out deprecated terms.
    terms = tmp_library.all_terms_in_domain(None)
    assert all(t.canonical != "Junk" for t in terms)


def test_delete_term_removes_aliases(tmp_library) -> None:
    """Deleting a term must clean up its aliases so they don't shadow new entries."""
    term_id = tmp_library.add_term(canonical="OldName", aliases=["OldAlias"])
    assert tmp_library.lookup_alias("OldAlias") is not None
    tmp_library.delete_term(term_id)
    assert tmp_library.lookup_alias("OldAlias") is None
    assert tmp_library.lookup_alias("OldName") is None


def test_add_speaker_appends_aliases_on_re_add(tmp_library) -> None:
    """Adding the same speaker again with new aliases extends, not duplicates."""
    tmp_library.add_speaker(
        canonical_name="Founder",
        display_label="Founder：",
        aliases=["Speaker 2"],
    )
    tmp_library.add_speaker(
        canonical_name="Founder",
        display_label="Founder：",
        aliases=["F", "boss"],
    )
    for alias in ("Speaker 2", "F", "boss"):
        hit = tmp_library.lookup_speaker(alias)
        assert hit is not None
        assert hit.canonical_name == "Founder"


def test_list_terms_pagination(tmp_library) -> None:
    """list_terms must respect limit so the UI doesn't paint thousands of rows."""
    for i in range(25):
        tmp_library.add_term(canonical=f"Term{i:02d}", aliases=[f"T{i:02d}"])
    rows = tmp_library.list_terms(limit=10)
    assert len(rows) == 10

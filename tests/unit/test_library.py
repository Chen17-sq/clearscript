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


def test_update_term_replaces_aliases(tmp_library) -> None:
    """update_term with aliases= replaces (not appends to) the alias set.

    The UI relies on this: when the user edits a term's aliases in the
    library panel and saves, they expect their list to win — not a union
    with what was there before.
    """
    term_id = tmp_library.add_term(
        canonical="Anthropic",
        aliases=["iShopee", "Anthropy"],
    )
    tmp_library.update_term(term_id, aliases=["Anthropic AI"])
    # Old aliases gone.
    assert tmp_library.lookup_alias("iShopee") is None
    assert tmp_library.lookup_alias("Anthropy") is None
    # New alias present.
    hit = tmp_library.lookup_alias("Anthropic AI")
    assert hit is not None
    assert hit.canonical == "Anthropic"


def test_update_term_changes_domain(tmp_library) -> None:
    term_id = tmp_library.add_term(canonical="Mem0", domain="ai-infra")
    tmp_library.update_term(term_id, domain="ai-product")
    hit = tmp_library.lookup_alias("Mem0")
    assert hit is not None
    assert hit.domain == "ai-product"


def test_update_speaker_changes_label(tmp_library) -> None:
    sid = tmp_library.add_speaker(
        canonical_name="Eileen",
        display_label="Eileen：",
        aliases=["Speaker 2"],
    )
    tmp_library.update_speaker(sid, display_label="Eileen (founder)：")
    hit = tmp_library.lookup_speaker("Speaker 2")
    assert hit is not None
    assert hit.display_label == "Eileen (founder)："


def test_lookup_alias_is_case_sensitive_by_design(tmp_library) -> None:
    """Aliases are stored verbatim. 'Tabby' and 'tabby' are not the same.

    ASR tools preserve casing so the canonical mapping must also — getting
    'tabby' back when the alias is 'Tabby' would let lowercase common words
    accidentally trigger corrections.
    """
    tmp_library.add_term(canonical="Tavily", aliases=["Tabby"])
    assert tmp_library.lookup_alias("Tabby") is not None
    # Lowercase variant isn't in the alias table.
    assert tmp_library.lookup_alias("tabby") is None


def test_negative_rules_idempotent(tmp_library) -> None:
    """Adding the same negative twice must not double-count."""
    tmp_library.add_negative(
        text="蛮好的",
        do_not_change_to="很好",
        reason="preserve colloquial style",
    )
    tmp_library.add_negative(
        text="蛮好的",
        do_not_change_to="很好",
        reason="preserve colloquial style",
    )
    negatives = tmp_library.list_negatives()
    # The library deduplicates by (text, do_not_change_to) — only one row.
    matching = [n for n in negatives if n["text"] == "蛮好的"]
    assert len(matching) == 1


def test_session_finish_records_tokens(tmp_library) -> None:
    sid = tmp_library.start_session(project_slug="t", provider="m", model="m1")
    tmp_library.finish_session(sid, input_tokens=1234, output_tokens=567)
    # The session row should be findable in stats.
    stats = tmp_library.stats()
    assert stats["sessions"] >= 1


# ============ Export / Import / Bulk ============


def test_export_dict_has_versioned_format(tmp_library) -> None:
    """The export must carry a format marker so future versions can detect
    incompatible files instead of silently corrupting state.
    """
    tmp_library.add_term(canonical="Tavily", aliases=["Tabby"])
    payload = tmp_library.export_dict()
    assert payload["format"] == "clearscript-library-export"
    assert "schema_version" in payload
    assert isinstance(payload["terms"], list)
    assert isinstance(payload["speakers"], list)


def test_export_dict_round_trip_through_import(tmp_library, tmp_path) -> None:
    """Export → write JSON → read JSON → import into fresh library must
    produce identical canonicals and alias mappings.
    """
    from clearscript.library import Library

    # Seed the source library with diverse content.
    tmp_library.add_term(canonical="Dify", aliases=["DeFi", "底牌"], type_="company")
    tmp_library.add_term(canonical="Tavily", aliases=["Tabby"], type_="company")
    tmp_library.add_speaker(
        canonical_name="Siqi",
        display_label="Siqi：",
        aliases=["Speaker 1"],
    )
    tmp_library.add_edit_pattern(
        title="Trim filler",
        trigger_desc="嗯/啊",
        action="drop",
        rationale="filler",
    )
    tmp_library.add_negative(text="蛮好的", do_not_change_to="很好")

    import json

    export_path = tmp_path / "export.json"
    export_path.write_text(
        json.dumps(tmp_library.export_dict(), ensure_ascii=False),
        encoding="utf-8",
    )

    # Import into a brand-new library.
    target = Library(tmp_path / "target.db")
    try:
        summary = target.import_dict(json.loads(export_path.read_text(encoding="utf-8")))
        assert summary["terms_added"] == 2
        assert summary["speakers_added"] == 1
        assert summary["patterns_added"] == 1
        assert summary["negatives_added"] == 1

        # Every alias resolves to the right canonical.
        for alias, canonical in [
            ("DeFi", "Dify"),
            ("底牌", "Dify"),
            ("Tabby", "Tavily"),
        ]:
            hit = target.lookup_alias(alias)
            assert hit is not None and hit.canonical == canonical

        spk = target.lookup_speaker("Speaker 1")
        assert spk is not None and spk.canonical_name == "Siqi"
    finally:
        target.close()


def test_import_dict_rejects_payload_without_format(tmp_library) -> None:
    """A random JSON file shouldn't be accepted — only well-formed exports."""
    import pytest

    with pytest.raises(ValueError, match="format"):
        tmp_library.import_dict({"terms": []})


def test_import_dict_merges_aliases_into_existing_term(tmp_library) -> None:
    """If the target library already has 'Tavily', importing more aliases
    for it must extend, not replace.
    """
    tmp_library.add_term(canonical="Tavily", aliases=["TablyAI"])
    payload = {
        "format": "clearscript-library-export",
        "schema_version": 1,
        "terms": [{"canonical": "Tavily", "aliases": ["Tabby", "Tably"]}],
        "speakers": [],
        "edit_patterns": [],
        "negatives": [],
    }
    summary = tmp_library.import_dict(payload)
    assert summary["terms_merged"] == 1
    assert summary["terms_added"] == 0
    # Both old and new aliases work.
    for alias in ("TablyAI", "Tabby", "Tably"):
        assert tmp_library.lookup_alias(alias).canonical == "Tavily"


def test_import_dict_skips_malformed_entries(tmp_library) -> None:
    """Empty or invalid records must be counted as skipped, not crash."""
    payload = {
        "format": "clearscript-library-export",
        "schema_version": 1,
        "terms": [
            {"canonical": "ValidTerm", "aliases": []},
            {"canonical": ""},  # skipped
            {},  # skipped
        ],
        "speakers": [
            {"canonical_name": "", "display_label": "x"},  # skipped
            {"canonical_name": "Real", "display_label": "Real：", "aliases": []},
        ],
        "edit_patterns": [
            {"title": "ok", "trigger_desc": "", "action": ""},  # skipped
        ],
        "negatives": [],
    }
    summary = tmp_library.import_dict(payload)
    assert summary["terms_added"] == 1
    assert summary["speakers_added"] == 1
    assert summary["skipped"] >= 3


def test_export_excludes_deprecated_terms(tmp_library) -> None:
    """Deprecated (rejected) terms must not leak into exports — otherwise
    sharing a library re-introduces the user's rejected entries.
    """
    keep_id = tmp_library.add_term(canonical="Keep", aliases=["keep"])
    drop_id = tmp_library.add_term(canonical="Drop", aliases=["drop"])
    tmp_library.reject_term(drop_id)

    payload = tmp_library.export_dict()
    canonicals = {t["canonical"] for t in payload["terms"]}
    assert "Keep" in canonicals
    assert "Drop" not in canonicals
    assert keep_id != drop_id  # sanity that they are distinct rows


def test_bulk_delete_terms_returns_count(tmp_library) -> None:
    a = tmp_library.add_term(canonical="A", aliases=["a"])
    b = tmp_library.add_term(canonical="B", aliases=["b"])
    c = tmp_library.add_term(canonical="C")

    deleted = tmp_library.bulk_delete_terms([a, b, 99_999])  # 99_999 doesn't exist
    assert deleted == 2  # only a and b
    # C still there.
    assert tmp_library.lookup_alias("C") is not None
    # A and B aliases gone via CASCADE.
    assert tmp_library.lookup_alias("a") is None
    assert tmp_library.lookup_alias("b") is None
    # Re-use c to satisfy linters.
    assert c > 0


def test_bulk_delete_terms_empty_list_is_safe(tmp_library) -> None:
    assert tmp_library.bulk_delete_terms([]) == 0


# ============ Health check ============


def test_health_check_detects_duplicate_alias_across_terms(tmp_library) -> None:
    """Same alias mapping to two canonicals is a real correctness risk —
    pipeline lookup becomes non-deterministic. Health check must surface it.
    """
    tmp_library.add_term(canonical="Foo", aliases=["common"])
    tmp_library.add_term(canonical="Bar", aliases=["common"])
    report = tmp_library.health_check()
    aliases = [d["alias"] for d in report["duplicate_aliases"]]
    assert "common" in aliases
    assert report["summary"]["duplicate_alias_groups"] >= 1


def test_health_check_detects_low_confidence_terms(tmp_library) -> None:
    """Terms whose confidence dropped below 0.3 (after rejection or never
    promoted from 'proposed') are surfaced for review.

    add_term inserts at confidence 0.5 with status='proposed', then we
    manually push it below threshold so the report flags it.
    """
    term_id = tmp_library.add_term(canonical="Sketchy", aliases=["maybe"])
    # Reject deprecates AND lowers confidence; we want a still-active,
    # low-confidence term, so update confidence directly.
    tmp_library._conn.execute(
        "UPDATE terms SET confidence = 0.1 WHERE id = ?", (term_id,)
    )
    report = tmp_library.health_check()
    canonicals = [t["canonical"] for t in report["low_confidence_terms"]]
    assert "Sketchy" in canonicals


def test_health_check_skips_deprecated_terms(tmp_library) -> None:
    """A rejected (deprecated) term must not show up in any health bucket.

    The user already told us they don't care about it — surfacing it as
    "low confidence" or "stale" would be noise.
    """
    term_id = tmp_library.add_term(canonical="Rejected", aliases=["rj"])
    tmp_library.reject_term(term_id)  # sets status=deprecated, drops confidence
    report = tmp_library.health_check()
    low = [t["canonical"] for t in report["low_confidence_terms"]]
    assert "Rejected" not in low


def test_health_check_reports_zero_when_clean(tmp_library) -> None:
    """Empty library produces all zeros — sanity check on the report shape."""
    report = tmp_library.health_check()
    s = report["summary"]
    assert s["duplicate_alias_groups"] == 0
    assert s["duplicate_canonical_groups"] == 0
    assert s["low_confidence_count"] == 0
    assert s["orphan_alias_count"] == 0


def test_health_check_stale_threshold_is_configurable(tmp_library) -> None:
    """stale_days parameter passed through to the report."""
    report = tmp_library.health_check(stale_days=30)
    assert report["stale_days_threshold"] == 30


def test_delete_negative_removes_row(tmp_library) -> None:
    tmp_library.add_negative(text="foo", do_not_change_to="bar")
    rows = tmp_library.list_negatives()
    assert len(rows) == 1
    target_id = rows[0]["id"]

    deleted = tmp_library.delete_negative(target_id)
    assert deleted is True
    assert tmp_library.list_negatives() == []


def test_delete_negative_missing_id_returns_false(tmp_library) -> None:
    assert tmp_library.delete_negative(99999) is False


# ============ Markdown export ============


def test_export_markdown_includes_terms_and_aliases(tmp_library) -> None:
    tmp_library.add_term(
        canonical="Tavily", aliases=["Tabby"], type_="company", domain="ai-infra"
    )
    md = tmp_library.export_markdown()
    assert "# clearscript library" in md
    assert "Tavily" in md
    assert "Tabby" in md
    # Domain heading appears.
    assert "ai-infra" in md


def test_export_markdown_groups_terms_by_domain(tmp_library) -> None:
    tmp_library.add_term(canonical="DomA_Term", domain="domA")
    tmp_library.add_term(canonical="DomB_Term", domain="domB")
    md = tmp_library.export_markdown()
    # Both domain headings exist.
    assert "domA" in md
    assert "domB" in md
    # DomA_Term comes before DomB_Term (alphabetic domain sort).
    assert md.index("DomA_Term") < md.index("DomB_Term")


def test_export_markdown_with_empty_library_has_just_headers(tmp_library) -> None:
    """Should not crash on empty library."""
    md = tmp_library.export_markdown()
    assert "# clearscript library" in md
    assert "## Terms" in md


def test_export_markdown_includes_speakers_and_patterns(tmp_library) -> None:
    tmp_library.add_speaker(canonical_name="Eileen", display_label="Eileen：")
    tmp_library.add_edit_pattern(
        title="Strip filler", trigger_desc="嗯", action="drop"
    )
    tmp_library.add_negative(text="蛮好的", do_not_change_to="很好")
    md = tmp_library.export_markdown()
    assert "## Speakers" in md
    assert "Eileen" in md
    assert "## Edit patterns" in md
    assert "Strip filler" in md
    assert "## Negative rules" in md
    assert "蛮好的" in md

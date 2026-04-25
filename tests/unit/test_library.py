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

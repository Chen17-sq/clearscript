"""Tests for the universal seed pack.

The seed pack installs ~17 well-known ASR mistakes (Dify←DeFi, Tavily←Tabby,
etc.) on first library open so users don't start from zero. It must be
idempotent — calling install twice should not duplicate aliases or terms.
"""

from __future__ import annotations

from clearscript.library.seed_pack import (
    SEED_NEGATIVES,
    SEED_TERMS,
    install_seed_pack,
    is_library_empty,
)


def test_seed_pack_has_expected_counts() -> None:
    """Sanity: don't accidentally lose seed entries in a refactor."""
    assert len(SEED_TERMS) >= 15, "seed pack should have at least 15 terms"
    assert len(SEED_NEGATIVES) >= 3, "seed pack should have at least 3 negatives"


def test_install_into_empty_library(tmp_library) -> None:
    assert is_library_empty(tmp_library)
    summary = install_seed_pack(tmp_library)
    assert summary["skipped"] is False
    assert summary["terms"] == len(SEED_TERMS)
    assert summary["negatives"] == len(SEED_NEGATIVES)
    assert not is_library_empty(tmp_library)


def test_lookup_finds_seeded_canonical(tmp_library) -> None:
    """The seed pack stores Dify as a canonical with DeFi as alias.

    Both should be looked up successfully — the canonical via
    ``lookup_alias("Dify")`` (which checks canonical names too), the alias
    via ``lookup_alias("DeFi")``.
    """
    install_seed_pack(tmp_library)
    by_alias = tmp_library.lookup_alias("DeFi")
    assert by_alias is not None
    assert by_alias.canonical == "Dify"
    by_canonical = tmp_library.lookup_alias("Dify")
    assert by_canonical is not None
    assert by_canonical.canonical == "Dify"


def test_install_skips_when_library_not_empty(tmp_library) -> None:
    tmp_library.add_term(canonical="MyCustomTerm", aliases=["MCT"])
    summary = install_seed_pack(tmp_library)
    assert summary["skipped"] is True
    assert summary["terms"] == 0
    # The user's own term must still be there.
    hit = tmp_library.lookup_alias("MCT")
    assert hit is not None and hit.canonical == "MyCustomTerm"


def test_force_install_overrides_skip(tmp_library) -> None:
    tmp_library.add_term(canonical="MyCustomTerm", aliases=["MCT"])
    summary = install_seed_pack(tmp_library, only_if_empty=False)
    assert summary["skipped"] is False
    assert summary["terms"] == len(SEED_TERMS)
    # The user's own term coexists with the seed pack.
    assert tmp_library.lookup_alias("MCT") is not None
    assert tmp_library.lookup_alias("DeFi") is not None


def test_install_is_idempotent(tmp_library) -> None:
    """Calling install twice (with only_if_empty=False) must not duplicate.

    SQLite UNIQUE constraints + ``INSERT OR IGNORE`` should make this safe.
    The total term count must stay the same after a second install.
    """
    install_seed_pack(tmp_library, only_if_empty=False)
    stats_before = tmp_library.stats()
    install_seed_pack(tmp_library, only_if_empty=False)
    stats_after = tmp_library.stats()
    assert stats_after["terms"] == stats_before["terms"]
    # Lookups still work — nothing got corrupted.
    assert tmp_library.lookup_alias("DeFi").canonical == "Dify"
    assert tmp_library.lookup_alias("Tabby").canonical == "Tavily"


def test_seeded_negatives_searchable(tmp_library) -> None:
    install_seed_pack(tmp_library)
    # Just verify the rows landed; we don't have a getter API for negatives,
    # but stats() reports the count.
    stats = tmp_library.stats()
    # Library.stats() reports the count under "negative_rules".
    assert stats.get("negative_rules", 0) >= len(SEED_NEGATIVES)

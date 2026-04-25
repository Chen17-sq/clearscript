"""Tests for the prompt loader."""

from __future__ import annotations

from clearscript.prompts import compose_edit_prompt, load_prompt


def test_loads_system_base() -> None:
    text = load_prompt("system_base")
    assert "clearscript" in text
    assert "Universal principles" in text


def test_loads_layer_files() -> None:
    for layer in (
        "l1_speaker",
        "l2_trim",
        "l3_asr_fix",
        "l3_5_sentence",
        "l4_preserve",
        "l5_format",
        "l6_punct",
    ):
        text = load_prompt(f"layers/{layer}")
        assert text.strip(), f"layer {layer} empty"


def test_compose_includes_all_layers() -> None:
    prompt = compose_edit_prompt(briefing_context="briefing-x", library_context="library-y")
    for marker in (
        "L1 SPEAKER",
        "L2 TRIM",
        "L3 ASR FIX",
        "L3 5 SENTENCE",
        "L4 PRESERVE",
        "L5 FORMAT",
        "L6 PUNCT",
    ):
        assert marker in prompt
    assert "briefing-x" in prompt
    assert "library-y" in prompt
    assert "## Session briefing" in prompt
    assert "## Library hints" in prompt


def test_compose_omits_empty_context() -> None:
    prompt = compose_edit_prompt()
    assert "## Session briefing" not in prompt
    assert "## Library hints" not in prompt

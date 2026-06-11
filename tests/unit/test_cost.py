"""Tests for the cost estimator."""

from __future__ import annotations

from clearscript.core.cost import actual_cost, estimate_cost, list_known_models


def test_anthropic_opus_estimate_is_in_expected_range() -> None:
    # 10k transcript tokens via Opus. The estimate now includes per-chunk
    # system-prompt overhead (~6k/chunk × 3 chunks) and the self-review
    # second pass (×1.35), so the honest total is ~$2 — the old ~$0.90
    # figure was the systematic undercount users complained about.
    transcript = "X" * 40_000  # ~10k tokens (chars/4)
    est = estimate_cost(
        transcript_text=transcript,
        provider_type="anthropic",
        model="claude-opus-4-7",
    )
    assert est.pricing_known
    assert 1.2 < est.total_cost_usd < 3.5
    assert est.input_tokens > 8000


def test_deepseek_chat_is_cheap() -> None:
    transcript = "X" * 40_000
    est = estimate_cost(
        transcript_text=transcript,
        provider_type="openai-compat",
        model="deepseek-chat",
    )
    assert est.pricing_known
    assert est.total_cost_usd < 0.05


def test_ollama_is_free() -> None:
    est = estimate_cost(
        transcript_text="hello world",
        provider_type="ollama",
        model="qwen2.5:14b",
    )
    assert est.pricing_known
    assert est.total_cost_usd == 0.0
    assert "local" in est.note


def test_unknown_model_returns_unknown_flag() -> None:
    est = estimate_cost(
        transcript_text="x" * 1000,
        provider_type="openai",
        model="gpt-99-imaginary",
    )
    assert not est.pricing_known
    assert est.total_cost_usd == 0.0
    assert "No pricing data" in est.note


def test_cjk_text_estimated_higher_than_ascii_for_same_chars() -> None:
    # 1000 CJK chars vs 1000 ASCII chars — CJK should produce more tokens
    cjk_est = estimate_cost(
        transcript_text="测" * 1000,
        provider_type="anthropic",
        model="claude-opus-4-7",
    )
    ascii_est = estimate_cost(
        transcript_text="X" * 1000,
        provider_type="anthropic",
        model="claude-opus-4-7",
    )
    assert cjk_est.input_tokens > ascii_est.input_tokens
    assert cjk_est.total_cost_usd > ascii_est.total_cost_usd


def test_known_models_listing_shape() -> None:
    known = list_known_models()
    assert "anthropic" in known
    assert "claude-opus-4-7" in known["anthropic"]
    assert "openai-compat" in known
    assert "deepseek-chat" in known["openai-compat"]


def test_actual_cost_with_known_pricing() -> None:
    """actual_cost uses REAL token counts (not estimates from char length)."""
    cost = actual_cost(
        provider_type="openai-compat",
        model="deepseek-v4-flash",
        input_tokens=10_000,
        output_tokens=5_000,
    )
    assert cost.pricing_known
    assert cost.input_tokens == 10_000
    # deepseek-v4-flash: $0.15/M input, $0.60/M output
    expected_in = 10_000 / 1_000_000 * 0.15
    expected_out = 5_000 / 1_000_000 * 0.60
    assert abs(cost.input_cost_usd - expected_in) < 1e-6
    assert abs(cost.output_cost_usd - expected_out) < 1e-6
    assert abs(cost.total_cost_usd - (expected_in + expected_out)) < 1e-6


def test_actual_cost_unknown_model_does_not_crash() -> None:
    cost = actual_cost(
        provider_type="openai",
        model="future-model-2030",
        input_tokens=1000,
        output_tokens=500,
    )
    assert not cost.pricing_known
    assert cost.total_cost_usd == 0.0
    assert cost.input_tokens == 1000  # token counts preserved for display
    assert cost.output_tokens_estimate == 500


def test_actual_cost_ollama_always_free() -> None:
    cost = actual_cost(
        provider_type="ollama",
        model="qwen2.5:14b",
        input_tokens=999_999,
        output_tokens=999_999,
    )
    assert cost.pricing_known
    assert cost.total_cost_usd == 0.0


def test_actual_cost_zero_tokens_returns_zero() -> None:
    cost = actual_cost(
        provider_type="anthropic",
        model="claude-opus-4-7",
        input_tokens=0,
        output_tokens=0,
    )
    assert cost.total_cost_usd == 0.0
    assert cost.input_tokens == 0


def test_actual_cost_anthropic_opus_scales_linearly() -> None:
    """Doubling tokens doubles cost."""
    one = actual_cost(
        provider_type="anthropic",
        model="claude-opus-4-7",
        input_tokens=1000,
        output_tokens=1000,
    )
    two = actual_cost(
        provider_type="anthropic",
        model="claude-opus-4-7",
        input_tokens=2000,
        output_tokens=2000,
    )
    assert abs(two.total_cost_usd - 2 * one.total_cost_usd) < 1e-6


def test_as_dict_round_trip() -> None:
    est = estimate_cost(
        transcript_text="x" * 1000,
        provider_type="anthropic",
        model="claude-opus-4-7",
    )
    payload = est.as_dict()
    for key in (
        "input_tokens",
        "output_tokens_estimate",
        "input_cost_usd",
        "output_cost_usd",
        "total_cost_usd",
        "pricing_known",
        "note",
    ):
        assert key in payload

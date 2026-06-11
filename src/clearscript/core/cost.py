"""Cost estimation for runs.

Lookup table of approximate per-1M-token USD prices (input / output) per
provider/model. Used by the web UI to show users an estimated cost
**before** they hit Run, so a long-doc + flagship-model combo never
surprises them.

The table is best-effort and lives in this file rather than a config so
contributions ship as code review. Update freely; refer to each provider's
public pricing page.
"""

from __future__ import annotations

from dataclasses import dataclass

from clearscript.core.chunking import estimate_tokens


@dataclass
class CostEstimate:
    input_tokens: int
    output_tokens_estimate: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    pricing_known: bool
    note: str = ""

    def as_dict(self) -> dict:
        return {
            "input_tokens": self.input_tokens,
            "output_tokens_estimate": self.output_tokens_estimate,
            "input_cost_usd": round(self.input_cost_usd, 5),
            "output_cost_usd": round(self.output_cost_usd, 5),
            "total_cost_usd": round(self.total_cost_usd, 5),
            "pricing_known": self.pricing_known,
            "note": self.note,
        }


# (input_per_1m, output_per_1m) in USD. Last refreshed 2026-04.
# Keys are provider TYPE (matches ProviderConfig.type), then model id.
_PRICING: dict[str, dict[str, tuple[float, float]]] = {
    "anthropic": {
        "claude-opus-4-7": (15.00, 75.00),
        "claude-sonnet-4-6": (3.00, 15.00),
        "claude-haiku-4-5": (0.80, 4.00),
        # Older / fallback
        "claude-3-5-sonnet-latest": (3.00, 15.00),
        "claude-3-5-haiku-latest": (0.80, 4.00),
    },
    "openai": {
        "gpt-4o": (2.50, 10.00),
        "gpt-4o-mini": (0.15, 0.60),
        "o1": (15.00, 60.00),
        "o1-mini": (3.00, 12.00),
    },
    "openai-compat": {
        # DeepSeek v4 series — current as of 2026-04. Verify exact USD
        # rates at https://api-docs.deepseek.com/quick_start/pricing —
        # values below are best-known approximations.
        "deepseek-v4-pro": (0.50, 2.00),
        "deepseek-v4-flash": (0.15, 0.60),
        # Legacy v3 (some users still pin to these via aliases)
        "deepseek-chat": (0.27, 1.10),
        "deepseek-reasoner": (0.55, 2.19),
        "moonshot-v1-128k": (8.40, 8.40),
        "qwen-plus": (1.10, 1.65),
        "qwen-max": (4.00, 12.00),
        "kimi-k2-0905-preview": (4.00, 16.00),
    },
    "google": {
        "gemini-2.0-flash-exp": (0.0, 0.0),
        "gemini-1.5-pro": (1.25, 5.00),
        "gemini-1.5-flash": (0.075, 0.30),
    },
    "ollama": {},  # local — always free
}

# Heuristic: with verbose models the cleaned output (markdown + JSON change
# log + JSON suggestions) typically runs 1.3–1.8x the input. 1.5 is the
# sweet spot — slightly conservative on the cost side. Real cost shown
# after the run reveals the truth.
_OUTPUT_RATIO = 1.5


# Fixed overhead the estimate must account for beyond the raw transcript:
# the composed system prompt (system_base + stage 04 + seven layer specs +
# library context) rides along with EVERY chunk (~6k tokens), and the
# self-review pass re-reads the whole output plus the change log. Ignoring
# these made estimates ~40-60% low — exactly the complaint that prompted
# the "tell me what it actually cost" feature.
_SYSTEM_PROMPT_TOKENS_PER_CHUNK = 6000
_CHUNK_SIZE_TOKENS = 3500  # mirrors chunking.DEFAULT_TARGET_TOKENS
_SELF_REVIEW_FACTOR = 1.35  # second pass reads output + changelog


def estimate_cost(
    *,
    transcript_text: str,
    provider_type: str,
    model: str,
    output_ratio: float = _OUTPUT_RATIO,
) -> CostEstimate:
    """Estimate cost for processing ``transcript_text`` with the given provider/model.

    Includes per-chunk system-prompt overhead and the self-review second
    pass, not just the transcript body.
    """
    transcript_tokens = estimate_tokens(transcript_text)
    est_chunks = max(1, -(-transcript_tokens // _CHUNK_SIZE_TOKENS))  # ceil div
    input_tokens = int(
        (transcript_tokens + est_chunks * _SYSTEM_PROMPT_TOKENS_PER_CHUNK)
        * _SELF_REVIEW_FACTOR
    )
    output_tokens = int(transcript_tokens * output_ratio * _SELF_REVIEW_FACTOR)

    provider_table = _PRICING.get(provider_type.lower(), {})
    pricing = provider_table.get(model)

    if pricing is None and provider_type.lower() == "ollama":
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens_estimate=output_tokens,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            total_cost_usd=0.0,
            pricing_known=True,
            note="Ollama runs locally — no API cost.",
        )

    if pricing is None:
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens_estimate=output_tokens,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            total_cost_usd=0.0,
            pricing_known=False,
            note=(
                f"No pricing data for {provider_type}/{model}. "
                "See your provider's pricing page; this is roughly "
                f"{input_tokens + output_tokens:,} total tokens."
            ),
        )

    input_per_1m, output_per_1m = pricing
    input_cost = (input_tokens / 1_000_000) * input_per_1m
    output_cost = (output_tokens / 1_000_000) * output_per_1m

    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens_estimate=output_tokens,
        input_cost_usd=input_cost,
        output_cost_usd=output_cost,
        total_cost_usd=input_cost + output_cost,
        pricing_known=True,
        note="",
    )


def list_known_models() -> dict[str, list[str]]:
    """Return every provider→models pair the price table knows about."""
    return {ptype: sorted(models.keys()) for ptype, models in _PRICING.items() if models}


def actual_cost(
    *,
    provider_type: str,
    model: str,
    input_tokens: int,
    output_tokens: int,
) -> CostEstimate:
    """Compute actual cost from real (post-run) token usage.

    Returns a ``CostEstimate`` shaped the same as ``estimate_cost`` so the
    UI can format both the same way; ``output_tokens_estimate`` here is
    actually the **real** output token count.
    """
    provider_table = _PRICING.get(provider_type.lower(), {})
    pricing = provider_table.get(model)

    if pricing is None and provider_type.lower() == "ollama":
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens_estimate=output_tokens,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            total_cost_usd=0.0,
            pricing_known=True,
            note="Ollama runs locally — no API cost.",
        )
    if pricing is None:
        return CostEstimate(
            input_tokens=input_tokens,
            output_tokens_estimate=output_tokens,
            input_cost_usd=0.0,
            output_cost_usd=0.0,
            total_cost_usd=0.0,
            pricing_known=False,
            note=f"No pricing data for {provider_type}/{model}.",
        )
    in_rate, out_rate = pricing
    in_cost = (input_tokens / 1_000_000) * in_rate
    out_cost = (output_tokens / 1_000_000) * out_rate
    return CostEstimate(
        input_tokens=input_tokens,
        output_tokens_estimate=output_tokens,
        input_cost_usd=in_cost,
        output_cost_usd=out_cost,
        total_cost_usd=in_cost + out_cost,
        pricing_known=True,
        note="",
    )

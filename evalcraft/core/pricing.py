"""Cache-aware cost estimation.

Prompt caching changed what an agent run costs. Providers bill cached input at a
steep discount and charge a premium to *write* the cache, so pricing every input
token at the full rate — which a flat ``prompt_tokens × input_rate`` does —
overstates the cost of a cache-heavy agent loop by up to an order of magnitude.
Agent loops are the worst case: most of the prompt is re-sent every turn and is
therefore cache-read, not fresh input.

Multipliers are expressed relative to the model's base *input* rate:

* ``cache_read`` — Anthropic bills cache reads at **0.1×** input. VERIFIED from
  Anthropic's prompt-caching pricing.
* ``cache_write`` — Anthropic bills 5-minute-TTL cache writes at **1.25×** input
  (1-hour TTL is 2×). VERIFIED. ``ANTHROPIC_CACHE_WRITE_1H`` is provided for
  callers that opt into the long TTL.
* OpenAI discounts cached input but does not bill a separate write premium; the
  read multiplier here is an **approximation** of the documented cached-input
  discount and is deliberately a named constant so it is easy to correct.

These are estimates in the same sense the per-model rate tables already are:
they apply only when a provider does not report an authoritative cost. When the
provider gives a real number, prefer it.
"""

from __future__ import annotations

# Relative to the base input rate.
ANTHROPIC_CACHE_READ = 0.1
ANTHROPIC_CACHE_WRITE = 1.25
ANTHROPIC_CACHE_WRITE_1H = 2.0

# OpenAI discounts cached input and charges no separate write premium.
OPENAI_CACHE_READ = 0.25
OPENAI_CACHE_WRITE = 1.0

# Used when a provider has no documented caching behaviour: cached tokens are
# billed as ordinary input, which reproduces the pre-cache behaviour exactly.
NO_CACHE_DISCOUNT = 1.0


def cache_adjusted_cost(
    *,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
    cache_read_multiplier: float = NO_CACHE_DISCOUNT,
    cache_write_multiplier: float = NO_CACHE_DISCOUNT,
) -> float:
    """Estimate the USD cost of one LLM call, pricing each cache tier separately.

    ``prompt_tokens`` must be **fresh, uncached** input (evalcraft's convention —
    see :class:`~evalcraft.core.models.TokenUsage`). With both cache counts at 0
    this is exactly ``(prompt × input + completion × output) / 1e6``, so cassettes
    recorded before cache segmentation price identically.
    """
    fresh = prompt_tokens * input_usd_per_mtok
    read = cache_read_tokens * input_usd_per_mtok * cache_read_multiplier
    write = cache_write_tokens * input_usd_per_mtok * cache_write_multiplier
    output = completion_tokens * output_usd_per_mtok
    return (fresh + read + write + output) / 1_000_000

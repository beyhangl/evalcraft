"""Tests for cache-segmented token accounting and cost estimation.

Prompt caching makes a flat prompt/completion split overstate the cost of an
agent loop by up to an order of magnitude. These tests pin the corrected
behaviour and — just as importantly — pin that cassettes recorded before cache
segmentation still price exactly as they did.
"""

import pytest

from evalcraft.core.models import Cassette, Span, SpanKind, TokenUsage
from evalcraft.core.pricing import (
    ANTHROPIC_CACHE_READ,
    ANTHROPIC_CACHE_WRITE,
    OPENAI_CACHE_READ,
    cache_adjusted_cost,
)

SONNET_IN, SONNET_OUT = 3.0, 15.0


def _legacy_cost(prompt, completion, in_rate=SONNET_IN, out_rate=SONNET_OUT):
    """The pre-cache formula, kept here as the back-compat oracle."""
    return (prompt * in_rate + completion * out_rate) / 1_000_000


# ── back-compat ──────────────────────────────────────────────────────────────

class TestBackCompat:
    @pytest.mark.parametrize("prompt,completion", [(0, 0), (1000, 100), (250_000, 4_000)])
    def test_zero_cache_matches_legacy_formula(self, prompt, completion):
        assert cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            prompt_tokens=prompt, completion_tokens=completion,
        ) == pytest.approx(_legacy_cost(prompt, completion))

    def test_legacy_token_usage_dict_loads(self):
        tu = TokenUsage.from_dict(
            {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120}
        )
        assert (tu.prompt_tokens, tu.total_tokens) == (100, 120)
        assert tu.cache_read_tokens == 0 and tu.cache_write_tokens == 0

    def test_multiplier_of_one_bills_cache_as_plain_input(self):
        # A provider with no documented caching discount must price identically.
        assert cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            prompt_tokens=500, completion_tokens=0, cache_read_tokens=500,
        ) == pytest.approx(_legacy_cost(1000, 0))


# ── the bug this fixes ───────────────────────────────────────────────────────

class TestCacheHeavyAgentLoop:
    def test_flat_pricing_overstates_a_cached_loop(self):
        """A realistic loop: 100k context, ~95% cache-read, small fresh delta."""
        segmented = cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            prompt_tokens=3_000, completion_tokens=500,
            cache_read_tokens=95_000, cache_write_tokens=2_000,
            cache_read_multiplier=ANTHROPIC_CACHE_READ,
            cache_write_multiplier=ANTHROPIC_CACHE_WRITE,
        )
        flat = _legacy_cost(100_000, 500)
        assert flat > segmented * 4  # materially overstated, not a rounding nit
        assert segmented == pytest.approx(
            (3_000 * 3 + 95_000 * 3 * 0.1 + 2_000 * 3 * 1.25 + 500 * 15) / 1_000_000
        )

    def test_cache_read_is_cheaper_than_fresh_input(self):
        fresh = cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            prompt_tokens=10_000,
        )
        cached = cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            cache_read_tokens=10_000, cache_read_multiplier=ANTHROPIC_CACHE_READ,
        )
        assert cached == pytest.approx(fresh * ANTHROPIC_CACHE_READ)

    def test_cache_write_carries_a_premium(self):
        fresh = cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            prompt_tokens=10_000,
        )
        written = cache_adjusted_cost(
            input_usd_per_mtok=SONNET_IN, output_usd_per_mtok=SONNET_OUT,
            cache_write_tokens=10_000, cache_write_multiplier=ANTHROPIC_CACHE_WRITE,
        )
        assert written > fresh
        assert written == pytest.approx(fresh * ANTHROPIC_CACHE_WRITE)


# ── TokenUsage model ─────────────────────────────────────────────────────────

class TestTokenUsageCacheFields:
    def test_round_trip_preserves_cache_fields(self):
        tu = TokenUsage(
            prompt_tokens=10, completion_tokens=5, total_tokens=115,
            cache_read_tokens=90, cache_write_tokens=10,
        )
        assert TokenUsage.from_dict(tu.to_dict()) == tu

    def test_cached_tokens_property(self):
        tu = TokenUsage(cache_read_tokens=90, cache_write_tokens=10)
        assert tu.cached_tokens == 100

    def test_cassette_totals_include_cached_tokens(self):
        c = Cassette(name="t")
        c.add_span(Span(
            kind=SpanKind.LLM_RESPONSE, model="m", cost_usd=0.01,
            token_usage=TokenUsage(
                prompt_tokens=10, completion_tokens=5, total_tokens=115,
                cache_read_tokens=90, cache_write_tokens=10,
            ),
        ))
        c.compute_metrics()
        assert c.total_tokens == 115  # cached tokens are real tokens


# ── recorder threading ───────────────────────────────────────────────────────

class TestRecorderThreadsCacheTokens:
    def test_record_llm_call_records_and_totals_cache_tokens(self):
        from evalcraft import CaptureContext

        with CaptureContext(name="cache") as ctx:
            ctx.record_llm_call(
                model="claude-sonnet-4", input="hi", output="yo",
                prompt_tokens=10, completion_tokens=5,
                cache_read_tokens=900, cache_write_tokens=90,
            )
        tu = ctx.cassette.spans[0].token_usage
        assert tu.cache_read_tokens == 900
        assert tu.cache_write_tokens == 90
        assert tu.total_tokens == 10 + 5 + 900 + 90

    def test_defaults_keep_legacy_total(self):
        from evalcraft import CaptureContext

        with CaptureContext(name="nocache") as ctx:
            ctx.record_llm_call(
                model="m", input="i", output="o",
                prompt_tokens=10, completion_tokens=5,
            )
        assert ctx.cassette.spans[0].token_usage.total_tokens == 15


# ── adapter extraction ───────────────────────────────────────────────────────

class TestAdapterExtraction:
    def test_anthropic_estimate_prices_cache_tiers(self):
        from evalcraft.adapters.anthropic_adapter import _estimate_cost

        cost = _estimate_cost(
            "claude-3-haiku-20240307", 1000, 100,
            cache_read_tokens=10_000, cache_write_tokens=1_000,
        )
        plain = _estimate_cost("claude-3-haiku-20240307", 1000, 100)
        assert cost > plain          # cached tokens still cost something
        # ...but far less than billing all 12k input tokens at the full rate
        assert cost < _estimate_cost("claude-3-haiku-20240307", 12_000, 100)

    def test_anthropic_unknown_model_still_returns_none(self):
        from evalcraft.adapters.anthropic_adapter import _estimate_cost

        assert _estimate_cost("not-a-model", 10, 10, cache_read_tokens=5) is None

    @pytest.mark.parametrize("bogus", [None, "12", object(), True])
    def test_int_or_zero_rejects_non_ints(self, bogus):
        # Users mock SDK usage objects; a MagicMock/None must never land in a
        # cassette as a token count.
        from evalcraft.adapters.anthropic_adapter import _int_or_zero

        assert _int_or_zero(bogus) == 0

    def test_int_or_zero_passes_real_ints(self):
        from evalcraft.adapters.anthropic_adapter import _int_or_zero

        assert _int_or_zero(42) == 42

    def test_openai_estimate_discounts_cached_input(self):
        from evalcraft.adapters.openai_adapter import _estimate_cost

        # caller has already subtracted cached tokens from prompt_tokens
        cached = _estimate_cost("gpt-4o", 1_000, 100, cache_read_tokens=9_000)
        full = _estimate_cost("gpt-4o", 10_000, 100)
        assert cached < full
        assert cached is not None and full is not None
        saving = (full - cached) / full
        assert 0 < saving < 1
        assert OPENAI_CACHE_READ < 1.0

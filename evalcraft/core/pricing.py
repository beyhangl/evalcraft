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

import re
from dataclasses import dataclass
from typing import TypeVar

T = TypeVar("T")

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


# ---------------------------------------------------------------------------
# Model lookup
# ---------------------------------------------------------------------------

# model id -> (input, output) USD per million tokens, optionally followed by
# (cache_read_multiplier, cache_write_multiplier) when they differ from the
# provider's default.
PriceTable = dict[str, tuple[float, ...]]


#: What may follow a listed id for the same model: a dated or numbered snapshot
#: (``-2024-07-18``, ``-20251001``, ``@20250929``, ``-0613``, ``-002``), a
#: preview or experimental tag, or ``-latest``. Anything else, such as ``-mini``,
#: ``-pro`` or ``-deep-research``, is a different model with its own price.
SNAPSHOT_SUFFIX = re.compile(
    r"^[-@](?:\d{8}|\d{4}-\d{2}-\d{2}|\d{3,4})(?:-preview)?$"
    r"|^-(?:latest|exp(?:-\d{2}-\d{2}|-\d{4})?|preview(?:-\d{2}-\d{2})?)$"
)


def match_model(table: dict[str, T], model: str) -> T | None:
    """Find ``model`` in ``table``: the exact id, else a listed id it is a snapshot of.

    Providers answer with dated snapshot ids (``gpt-4o-mini-2024-07-18``), so a
    listed id also covers its snapshots. A different model that merely shares a
    prefix (``gpt-4o-mini`` vs ``gpt-4o``, ``o3-pro`` vs ``o3``, ``gpt-5.5`` vs
    ``gpt-5``) is never matched, so it can't borrow another model's price.
    """
    if model in table:
        return table[model]
    for key in table:
        if model.startswith(key) and SNAPSHOT_SUFFIX.match(model[len(key):]):
            return table[key]
    return None


@dataclass(frozen=True)
class ModelPrice:
    """USD per million tokens, with cache tiers relative to the input rate."""

    input_usd_per_mtok: float
    output_usd_per_mtok: float
    cache_read_multiplier: float = NO_CACHE_DISCOUNT
    cache_write_multiplier: float = NO_CACHE_DISCOUNT

    def cost(
        self,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_read_tokens: int = 0,
        cache_write_tokens: int = 0,
    ) -> float:
        return cache_adjusted_cost(
            input_usd_per_mtok=self.input_usd_per_mtok,
            output_usd_per_mtok=self.output_usd_per_mtok,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            cache_read_tokens=cache_read_tokens,
            cache_write_tokens=cache_write_tokens,
            cache_read_multiplier=self.cache_read_multiplier,
            cache_write_multiplier=self.cache_write_multiplier,
        )


def entry_price(entry: tuple[float, ...], default_read: float, default_write: float) -> ModelPrice:
    """Build a :class:`ModelPrice` from a :data:`PriceTable` entry."""
    read = entry[2] if len(entry) > 2 else default_read
    write = entry[3] if len(entry) > 3 else default_write
    return ModelPrice(entry[0], entry[1], read, write)


_REGISTERED: dict[str, ModelPrice] = {}


def registered_price(model: str) -> ModelPrice | None:
    """A price set with :func:`register_price` for ``model`` or its snapshots."""
    return match_model(_REGISTERED, model)


def resolve_price(
    model: str, table: PriceTable, default_read: float, default_write: float
) -> ModelPrice | None:
    """Price ``model`` from registered prices and one provider ``table``.

    An exact id wins over a snapshot match, and a registered price wins over
    the table at the same level, so registering ``gpt-4o`` overrides
    ``gpt-4o`` and its snapshots but never touches ``gpt-4o-mini``.
    """
    if model in _REGISTERED:
        return _REGISTERED[model]
    if model in table:
        return entry_price(table[model], default_read, default_write)
    found = registered_price(model)
    if found is not None:
        return found
    entry = match_model(table, model)
    return entry_price(entry, default_read, default_write) if entry is not None else None


def register_price(
    model: str,
    *,
    input_usd_per_mtok: float,
    output_usd_per_mtok: float,
    cached_input_usd_per_mtok: float | None = None,
    cache_write_usd_per_mtok: float | None = None,
) -> None:
    """Price a model evalcraft doesn't know, or override a built-in price.

    Registered prices win over the built-in tables and also cover dated
    snapshots of ``model``. Cached-input and cache-write prices default to the
    plain input price. ``[tool.evalcraft.prices]`` in ``pyproject.toml`` calls
    this for each entry when the pytest plugin starts.
    """
    if input_usd_per_mtok < 0 or output_usd_per_mtok < 0:
        raise ValueError("prices must not be negative")
    base = input_usd_per_mtok

    def _mult(value: float | None) -> float:
        if value is None or base == 0:
            return NO_CACHE_DISCOUNT
        if value < 0:
            raise ValueError("prices must not be negative")
        return value / base

    _REGISTERED[model] = ModelPrice(
        input_usd_per_mtok=input_usd_per_mtok,
        output_usd_per_mtok=output_usd_per_mtok,
        cache_read_multiplier=_mult(cached_input_usd_per_mtok),
        cache_write_multiplier=_mult(cache_write_usd_per_mtok),
    )


def clear_registered_prices() -> None:
    """Forget every :func:`register_price` entry (mainly for tests)."""
    _REGISTERED.clear()


#: Provider prefixes some frameworks put in front of a model id
#: (``openai:gpt-4o``, ``anthropic:claude-…``). A fine-tune id (``ft:…``) or an
#: Ollama ``name:tag`` is not one of these and is never stripped.
PROVIDER_PREFIX = re.compile(
    r"^(?:openai|anthropic|google-gla|google-vertex|google|gemini|vertexai|groq|"
    r"mistral|bedrock|azure|openrouter|cohere|deepseek|xai)[:/]",
    re.IGNORECASE,
)


def strip_provider(model: str) -> str:
    """``model`` without a framework provider prefix or a ``models/`` prefix."""
    return PROVIDER_PREFIX.sub("", model, count=1).removeprefix("models/")


def price_for(model: str | None) -> ModelPrice | None:
    """The price evalcraft would use for ``model``, or ``None`` if unknown.

    Registered prices first (checked against the id exactly as recorded, so a
    fine-tune id can be priced), then the OpenAI, Anthropic and Gemini tables.
    """
    if not model:
        return None
    if model in _REGISTERED:
        return _REGISTERED[model]
    name = strip_provider(model)
    # Imported here: the adapters import this module.
    from evalcraft.adapters import anthropic_adapter, gemini_adapter, openai_adapter

    for table, read, write in (
        (openai_adapter._MODEL_PRICING, OPENAI_CACHE_READ, OPENAI_CACHE_WRITE),
        (anthropic_adapter._MODEL_PRICING, ANTHROPIC_CACHE_READ, ANTHROPIC_CACHE_WRITE),
        (gemini_adapter._MODEL_PRICING, NO_CACHE_DISCOUNT, NO_CACHE_DISCOUNT),
    ):
        price = resolve_price(name, table, read, write)
        if price is not None:
            return price
    return None


# Model ids that are clearly paid provider models. A call to one of these with
# tokens but no price is a gap in the price table, not a free call. Open-weight
# names (``gpt-oss``) and local ``name:tag`` ids (Ollama) are not counted.
PAID_MODEL_PATTERN = re.compile(
    r"^(?:ft:)?(?:gpt-(?!oss)|chatgpt-|o\d+(?:-|$)|claude-|gemini-|grok-)",
    re.IGNORECASE,
)


def looks_paid(model: str | None) -> bool:
    """Whether ``model`` names a hosted, paid provider model."""
    if not model:
        return False
    name = strip_provider(model)
    if ":" in name and not name.startswith("ft:"):
        return False
    return bool(PAID_MODEL_PATTERN.match(name))

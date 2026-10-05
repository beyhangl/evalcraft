"""Opaque reasoning state — capture and integrity checking.

Reasoning models return content the caller cannot interpret but **must** send
back verbatim: Anthropic extended-thinking blocks carry a cryptographic
``signature``, and OpenAI's Responses API returns ``reasoning.encrypted_content``.
Providers reject or silently degrade a follow-up turn whose reasoning state was
dropped or altered.

That makes this a correctness issue for replay, not a fidelity nicety: a cassette
recorded from a reasoning model *without* its reasoning blocks is not a faithful
recording, and replaying it is invalid rather than merely lossy. This module
detects that situation so it can be reported loudly instead of silently trusted.

Detection is deliberately conservative — it only flags a span when the model's
provider requires its reasoning state back, so ordinary cassettes are never
false-flagged.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - typing only
    from evalcraft.core.models import Cassette, Span

#: Span-metadata key under which adapters store captured reasoning blocks.
REASONING_METADATA_KEY = "reasoning"

#: Substrings identifying models whose recordings are invalid without their
#: reasoning state. Matched case-insensitively against the recorded model name.
#:
#: Only models whose provider *requires* the reasoning to be sent back belong
#: here. OpenAI's o-series and GPT-5/6 families are deliberately absent: OpenAI
#: recommends passing ``encrypted_content`` back but does not require it, and
#: Chat Completions never returns it, so a recording without it is complete.
#: DeepSeek rejects ``reasoning_content`` in input, so ``*-reasoner`` is absent
#: too. Claude 4.x is absent because thinking is opt-in there.
REASONING_MODEL_MARKERS: tuple[str, ...] = (
    "thinking",                    # explicit extended-thinking variants
    # Claude Opus 5.5 (2026-09-22) and Fable 5.1 think on every turn and can't
    # disable it, so a recording without their thinking blocks is degraded.
    "claude-opus-5-5",
    "claude-fable-5-1",
)


def is_reasoning_model(model: str | None) -> bool:
    """Whether ``model`` names a family known to emit opaque reasoning state."""
    if not model:
        return False
    name = model.lower()
    return any(marker in name for marker in REASONING_MODEL_MARKERS)


def span_has_reasoning_state(span: Span) -> bool:
    """Whether ``span`` carries captured reasoning blocks."""
    blocks = (span.metadata or {}).get(REASONING_METADATA_KEY)
    return bool(blocks)


def find_degraded_reasoning_spans(cassette: Cassette) -> list[Span]:
    """Return LLM spans recorded from a reasoning model with no reasoning state.

    These are the spans whose replay is invalid rather than merely lossy: the
    provider will reject or silently degrade the turn because the signed
    reasoning block it requires is absent.
    """
    from evalcraft.core.models import SpanKind

    return [
        span for span in cassette.spans
        if span.kind in (SpanKind.LLM_REQUEST, SpanKind.LLM_RESPONSE)
        and is_reasoning_model(span.model)
        and not span_has_reasoning_state(span)
    ]

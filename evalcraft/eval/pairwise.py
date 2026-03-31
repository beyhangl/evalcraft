"""Pairwise comparison evaluation — Arena-style A/B scoring.

Instead of scoring a single output on a rubric, present two outputs
side-by-side and have an LLM judge pick the better one.  This mirrors
human decision-making and produces more reliable rankings than
pointwise scoring.

Usage::

    from evalcraft.eval.pairwise import pairwise_compare, pairwise_rank

    result = pairwise_compare(
        cassette_a, cassette_b,
        criteria="Which response is more helpful and accurate?",
    )
    print(result.winner)   # "A", "B", or "tie"
    print(result.reason)

    # Rank multiple cassettes via round-robin tournament
    rankings = pairwise_rank(
        [cassette_a, cassette_b, cassette_c],
        criteria="Helpfulness and accuracy",
    )
    for entry in rankings:
        print(f"{entry.name}: {entry.wins}W {entry.losses}L (score {entry.score:.2f})")
"""

from __future__ import annotations

import json
import random
from dataclasses import dataclass, field
from typing import Any

from evalcraft.core.models import AgentRun, Cassette


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _get_cassette(obj: Cassette | AgentRun) -> Cassette:
    if isinstance(obj, AgentRun):
        return obj.cassette
    return obj


def _call_pairwise_judge(
    prompt: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call an LLM to compare two outputs."""
    resolved_model = model

    if provider == "openai":
        try:
            import openai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for pairwise comparison. "
                "Install it with: pip install 'evalcraft[openai]'"
            ) from exc

        resolved_model = resolved_model or "gpt-4.1-nano"
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        client = openai.OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=temperature,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a fair evaluation judge comparing two agent outputs. "
                        "You MUST respond ONLY with a JSON object: "
                        '{"winner": "A" or "B" or "tie", "reason": "brief explanation", '
                        '"confidence": 0.0-1.0}'
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        raw = response.choices[0].message.content or "{}"

    elif provider == "anthropic":
        try:
            import anthropic  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for pairwise comparison. "
                "Install it with: pip install 'evalcraft[anthropic]'"
            ) from exc

        resolved_model = resolved_model or "claude-haiku-4-5-20251001"
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        client = anthropic.Anthropic(**kwargs)
        response = client.messages.create(
            model=resolved_model,
            max_tokens=512,
            temperature=temperature,
            system=(
                "You are a fair evaluation judge comparing two agent outputs. "
                "You MUST respond ONLY with a JSON object: "
                '{"winner": "A" or "B" or "tie", "reason": "brief explanation", '
                '"confidence": 0.0-1.0}'
            ),
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.content[0].text if response.content else "{}"
    else:
        raise ValueError(f"Unsupported provider: {provider!r}")

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"winner": "tie", "reason": f"Judge returned invalid JSON: {raw[:200]}", "confidence": 0.0}

    result.setdefault("winner", "tie")
    result.setdefault("reason", "")
    result.setdefault("confidence", 0.5)

    # Normalise winner value
    winner = str(result["winner"]).strip().upper()
    if winner not in ("A", "B", "TIE"):
        winner = "TIE"
    result["winner"] = winner.lower() if winner == "TIE" else winner

    return result


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PairwiseResult:
    """Result of comparing two cassettes."""
    winner: str  # "A", "B", or "tie"
    reason: str = ""
    confidence: float = 0.5
    output_a: str = ""
    output_b: str = ""
    swapped: bool = False  # True if presentation order was randomized

    def to_dict(self) -> dict:
        return {
            "winner": self.winner,
            "reason": self.reason,
            "confidence": self.confidence,
            "output_a": self.output_a[:200],
            "output_b": self.output_b[:200],
            "swapped": self.swapped,
        }


@dataclass
class RankingEntry:
    """One entry in a pairwise ranking leaderboard."""
    name: str
    wins: int = 0
    losses: int = 0
    ties: int = 0
    score: float = 0.0  # wins / (wins + losses + ties)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "wins": self.wins,
            "losses": self.losses,
            "ties": self.ties,
            "score": self.score,
        }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def pairwise_compare(
    cassette_a: Cassette | AgentRun,
    cassette_b: Cassette | AgentRun,
    criteria: str,
    *,
    randomize_order: bool = True,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> PairwiseResult:
    """Compare two cassettes and pick a winner using an LLM judge.

    To mitigate position bias, the presentation order is randomized by
    default (``randomize_order=True``).  The result always maps back to
    the original A/B labels.

    Args:
        cassette_a: First cassette (labeled "A").
        cassette_b: Second cassette (labeled "B").
        criteria: What to evaluate (e.g. "helpfulness", "accuracy").
        randomize_order: Randomize which output is shown first (default True).
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.
    """
    ca = _get_cassette(cassette_a)
    cb = _get_cassette(cassette_b)
    output_a = ca.output_text
    output_b = cb.output_text

    # Randomize to mitigate position bias
    swapped = False
    if randomize_order:
        swapped = random.random() < 0.5

    if swapped:
        first_output, second_output = output_b, output_a
    else:
        first_output, second_output = output_a, output_b

    prompt = (
        f"## Criteria\n{criteria}\n\n"
        f"## Output A\n{first_output}\n\n"
        f"## Output B\n{second_output}\n\n"
        "Which output is better according to the criteria? "
        "Pick 'A', 'B', or 'tie' if they are equally good."
    )

    result = _call_pairwise_judge(prompt, provider=provider, model=model, api_key=api_key)

    winner = result["winner"]
    # Unswap if needed
    if swapped and winner in ("A", "B"):
        winner = "B" if winner == "A" else "A"

    return PairwiseResult(
        winner=winner,
        reason=result.get("reason", ""),
        confidence=float(result.get("confidence", 0.5)),
        output_a=output_a,
        output_b=output_b,
        swapped=swapped,
    )


def pairwise_rank(
    cassettes: list[Cassette | AgentRun],
    criteria: str,
    *,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
) -> list[RankingEntry]:
    """Rank multiple cassettes via round-robin pairwise tournament.

    Every cassette is compared against every other cassette once.
    Results are aggregated into a leaderboard sorted by win rate.

    Args:
        cassettes: List of cassettes to rank.
        criteria: Evaluation criteria for comparisons.
        provider: LLM provider.
        model: Override the judge model.
        api_key: Optional API key override.

    Returns:
        List of RankingEntry sorted by score (highest first).
    """
    if len(cassettes) < 2:
        entries = []
        for c in cassettes:
            name = _get_cassette(c).name or "unnamed"
            entries.append(RankingEntry(name=name, score=1.0))
        return entries

    # Build entries
    entries: dict[int, RankingEntry] = {}
    for i, c in enumerate(cassettes):
        name = _get_cassette(c).name or f"cassette_{i}"
        entries[i] = RankingEntry(name=name)

    # Round-robin tournament
    for i in range(len(cassettes)):
        for j in range(i + 1, len(cassettes)):
            result = pairwise_compare(
                cassettes[i], cassettes[j],
                criteria=criteria,
                provider=provider,
                model=model,
                api_key=api_key,
            )
            if result.winner == "A":
                entries[i].wins += 1
                entries[j].losses += 1
            elif result.winner == "B":
                entries[j].wins += 1
                entries[i].losses += 1
            else:
                entries[i].ties += 1
                entries[j].ties += 1

    # Compute scores
    for entry in entries.values():
        total = entry.wins + entry.losses + entry.ties
        entry.score = entry.wins / total if total > 0 else 0.0

    # Sort by score descending
    return sorted(entries.values(), key=lambda e: e.score, reverse=True)

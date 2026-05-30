"""Shared utilities for eval scorers — DRY helpers used across all eval modules."""

from __future__ import annotations

import json
from typing import Any

from evalcraft.core.models import AgentRun, Cassette


def get_cassette(obj: Cassette | AgentRun) -> Cassette:
    """Extract cassette from either a Cassette or AgentRun."""
    if isinstance(obj, AgentRun):
        return obj.cassette
    return obj


def call_llm_judge(
    prompt: str,
    *,
    system_prompt: str,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> dict[str, Any]:
    """Call an LLM judge with a given system prompt and parse the JSON response.

    This is the shared backbone for all LLM-as-Judge scorers. Each scorer
    provides its own system prompt and user prompt; this function handles
    the provider dispatch, API call, and response parsing.

    If a judge cache is active (via
    ``evalcraft.eval.judge_cache.use_judge_cache`` or the ``EVALCRAFT_JUDGE_CACHE``
    env var) a recorded response is replayed at $0 instead of calling the model.
    See that module for modes and the staleness caveat.

    Returns a dict parsed from the judge's JSON response.
    """
    from evalcraft.eval.judge_cache import JudgeCache, JudgeCacheMiss, resolve_judge_cache

    cache = resolve_judge_cache()
    cache_key: str | None = None
    if cache is not None:
        cache_key = JudgeCache.make_key(
            provider=provider,
            model=model,
            system_prompt=system_prompt,
            prompt=prompt,
            temperature=temperature,
        )
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
        if cache.mode == "replay":
            raise JudgeCacheMiss(
                "No cached judge response for this call (judge cache is in "
                "'replay' mode). Re-record with mode 'record' or 'auto'."
            )

    raw = _provider_call(
        prompt,
        system_prompt=system_prompt,
        provider=provider,
        model=model,
        api_key=api_key,
        temperature=temperature,
    )

    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        result = {"pass": False, "reason": f"Judge returned invalid JSON: {raw[:200]}"}

    if cache is not None and cache_key is not None:
        cache.put(cache_key, result)

    return result


def _provider_call(
    prompt: str,
    *,
    system_prompt: str,
    provider: str = "openai",
    model: str | None = None,
    api_key: str | None = None,
    temperature: float = 0.0,
) -> str:
    """Dispatch to the provider SDK and return the raw judge response string.

    Isolated from :func:`call_llm_judge` so caching and parsing wrap a single,
    well-defined network boundary (and so tests can stub the network here).
    """
    resolved_model = model

    if provider == "openai":
        try:
            import openai  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'openai' package is required for LLM-as-Judge scorers. "
                "Install it with: pip install 'evalcraft[openai]'"
            ) from exc

        resolved_model = resolved_model or "gpt-5.4-nano"
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        client: Any = openai.OpenAI(**kwargs)
        response = client.chat.completions.create(
            model=resolved_model,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            response_format={"type": "json_object"},
        )
        return response.choices[0].message.content or "{}"

    if provider == "anthropic":
        try:
            import anthropic  # type: ignore[import]
        except ImportError as exc:
            raise ImportError(
                "The 'anthropic' package is required for LLM-as-Judge scorers. "
                "Install it with: pip install 'evalcraft[anthropic]'"
            ) from exc

        resolved_model = resolved_model or "claude-haiku-4-5-20251001"
        kwargs = {}
        if api_key:
            kwargs["api_key"] = api_key
        client = anthropic.Anthropic(**kwargs)
        response = client.messages.create(
            model=resolved_model,
            max_tokens=1024,
            temperature=temperature,
            system=system_prompt,
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text if response.content else "{}"

    raise ValueError(f"Unsupported judge provider: {provider!r} (use 'openai' or 'anthropic')")


def normalize_pass_key(result: dict[str, Any]) -> dict[str, Any]:
    """Normalise the 'pass' key in a judge result dict.

    Some models return 'passed', 'result', or 'verdict' instead of 'pass'.
    This function ensures a consistent 'pass' key exists.
    """
    if "pass" not in result:
        for alt_key in ("passed", "result", "verdict"):
            if alt_key in result:
                result["pass"] = bool(result[alt_key])
                break
        else:
            result["pass"] = False

    result.setdefault("reason", "")
    result.setdefault("score", 1.0 if result["pass"] else 0.0)
    return result

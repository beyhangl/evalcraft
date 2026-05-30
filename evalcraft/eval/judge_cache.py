"""Opt-in record/replay cache for LLM-as-Judge calls.

LLM-as-Judge / RAG / pairwise scorers call a real model at evaluation time, so
they cost money and are non-deterministic (see ``docs/user-guide/scorers.md``).
This module lets you **record judge responses once and replay them at $0** in CI,
keyed by a hash of (provider, model, system prompt, prompt, temperature).

Opt-in — disabled by default. Two ways to enable:

1. Context manager (recommended)::

       from evalcraft.eval.judge_cache import use_judge_cache

       with use_judge_cache("tests/judge_cache.json"):       # mode="auto"
           result = assert_output_semantic(run, criteria="mentions Paris")

2. Environment variable (e.g. in CI)::

       EVALCRAFT_JUDGE_CACHE=tests/judge_cache.json
       EVALCRAFT_JUDGE_CACHE_MODE=replay   # optional: auto | record | replay

Modes:

- ``auto``   — read from cache; on a miss, call the model and store the result.
- ``record`` — always call the model and overwrite the cached entry.
- ``replay`` — read-only; a cache miss raises :class:`JudgeCacheMiss` so CI is
  fully deterministic and never makes a surprise paid call.

.. warning::
    A cached judgment is **frozen** — exactly like a cassette. It will not
    reflect changes in the judge model or prompt until you re-record (``record``
    / ``auto``). This trades determinism for staleness; see the fingerprint and
    staleness notes in the docs.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

ENV_CACHE_PATH = "EVALCRAFT_JUDGE_CACHE"
ENV_CACHE_MODE = "EVALCRAFT_JUDGE_CACHE_MODE"

_VALID_MODES = ("auto", "record", "replay")


class JudgeCacheMiss(RuntimeError):  # noqa: N818 - "Miss" reads clearer than "MissError"
    """Raised in ``replay`` mode when a judge call has no cached entry."""


class JudgeCache:
    """A disk-backed record/replay cache for judge responses."""

    def __init__(self, path: str | Path, mode: str = "auto") -> None:
        if mode not in _VALID_MODES:
            raise ValueError(f"Invalid judge-cache mode {mode!r} (use one of {_VALID_MODES})")
        self.path = Path(path)
        self.mode = mode
        self._store: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                loaded = json.loads(self.path.read_text())
                if isinstance(loaded, dict):
                    self._store = loaded
            except (json.JSONDecodeError, OSError):
                self._store = {}

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._store, indent=2, sort_keys=True, default=str))

    @staticmethod
    def make_key(
        *,
        provider: str,
        model: str | None,
        system_prompt: str,
        prompt: str,
        temperature: float,
    ) -> str:
        basis = json.dumps(
            {
                "provider": provider,
                "model": model or "",
                "system_prompt": system_prompt,
                "prompt": prompt,
                "temperature": temperature,
            },
            sort_keys=True,
            default=str,
        )
        return hashlib.sha256(basis.encode()).hexdigest()

    def get(self, key: str) -> dict | None:
        """Return a cached result, or None. In ``record`` mode always None."""
        if self.mode == "record":
            return None
        value = self._store.get(key)
        return dict(value) if isinstance(value, dict) else None

    def put(self, key: str, result: dict) -> None:
        """Store a result and persist. In ``replay`` mode this is a no-op."""
        if self.mode == "replay":
            return
        self._store[key] = result
        self._persist()

    def __len__(self) -> int:
        return len(self._store)


# Context-local active cache (set by ``use_judge_cache``).
_active: contextvars.ContextVar[JudgeCache | None] = contextvars.ContextVar(
    "_active_judge_cache", default=None
)


def get_active_judge_cache() -> JudgeCache | None:
    """Return the cache set by ``use_judge_cache`` for the current context."""
    return _active.get()


@contextlib.contextmanager
def use_judge_cache(path: str | Path, mode: str = "auto") -> Iterator[JudgeCache]:
    """Activate a judge cache for the duration of the ``with`` block."""
    cache = JudgeCache(path, mode=mode)
    token = _active.set(cache)
    try:
        yield cache
    finally:
        _active.reset(token)


def resolve_judge_cache() -> JudgeCache | None:
    """Resolve the cache to use: the active context cache, else the env var.

    Returns None when caching is not enabled (the default).
    """
    active = _active.get()
    if active is not None:
        return active
    env_path = os.environ.get(ENV_CACHE_PATH)
    if env_path:
        return JudgeCache(env_path, mode=os.environ.get(ENV_CACHE_MODE, "auto"))
    return None

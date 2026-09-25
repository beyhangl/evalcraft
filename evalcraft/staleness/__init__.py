"""Staleness detection — flag cassettes recorded against retired models / drifted prompts.

A cassette's recorded provenance (model set, prompt hash, timestamp) is only
useful if something acts on it. This module does: it turns that provenance into
actionable CI signal so a deterministic test can't silently keep passing against
a model that no longer exists.

    from evalcraft.staleness import StalenessChecker
"""

from evalcraft.core.models import compute_prompt_hash
from evalcraft.staleness.checker import (
    StalenessChecker,
    StalenessFinding,
    StalenessReport,
    find_alias_moves,
    hash_prompts_file,
)
from evalcraft.staleness.volatile import VolatileValue, find_volatile_values

__all__ = [
    "StalenessChecker",
    "StalenessFinding",
    "StalenessReport",
    "VolatileValue",
    "compute_prompt_hash",
    "find_alias_moves",
    "find_volatile_values",
    "hash_prompts_file",
]

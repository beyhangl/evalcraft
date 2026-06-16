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
    hash_prompts_file,
)

__all__ = [
    "StalenessChecker",
    "StalenessFinding",
    "StalenessReport",
    "compute_prompt_hash",
    "hash_prompts_file",
]

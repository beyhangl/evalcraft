"""Project policy from ``[tool.evalcraft]`` in ``pyproject.toml``.

Keeping the policy in the repository means ``evalcraft check-stale`` and the
pytest plugin agree on it, and CI needs no long command lines::

    [tool.evalcraft]
    expire_after_days = 90            # older recordings fail (check-stale and pytest in CI)
    max_age_days = 30                 # older recordings get an INFO note
    models = ["gpt-5.1", "claude-sonnet-4-5"]
    tools = "tests/tools.json"        # paths are relative to pyproject.toml
    prompts = "tests/prompts.json"

Command-line flags override these values. The table is read from the nearest
``pyproject.toml`` that has one, searching upwards but not past the repository
root, so a sub-package's own ``pyproject.toml`` doesn't hide the policy.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised on 3.10 only
    import tomli as tomllib

KNOWN_KEYS = ("expire_after_days", "max_age_days", "models", "tools", "prompts")


class ConfigError(ValueError):
    """``[tool.evalcraft]`` holds a value evalcraft can't use."""


@dataclass
class EvalcraftConfig:
    expire_after_days: int | None = None
    max_age_days: int | None = None
    models: list[str] | None = None
    tools: Path | None = None
    prompts: Path | None = None
    source: Path | None = field(default=None, compare=False)
    # Keys evalcraft doesn't know, likely typos or options from a newer version.
    unknown_keys: list[str] = field(default_factory=list, compare=False)


def _read(path: Path) -> dict[str, Any]:
    try:
        with path.open("rb") as fh:
            return tomllib.load(fh)
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: {exc}") from exc


def find_pyproject(start: Path | None = None) -> tuple[Path, dict[str, Any]] | None:
    """Find the nearest ``pyproject.toml`` with a ``[tool.evalcraft]`` table.

    Searches ``start`` (default: cwd) and its parents, stopping after the first
    directory that contains ``.git``. Returns the path and its parsed contents.
    """
    here = (start or Path.cwd()).resolve()
    for directory in (here, *here.parents):
        candidate = directory / "pyproject.toml"
        if candidate.is_file():
            data = _read(candidate)
            if "evalcraft" in data.get("tool", {}):
                return candidate, data
        if (directory / ".git").exists():
            break
    return None


def _positive_int(key: str, value: Any, source: Path) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ConfigError(f"{source}: [tool.evalcraft] {key} must be a positive integer")
    return value


def load_config(start: Path | None = None) -> EvalcraftConfig:
    """Read ``[tool.evalcraft]`` (see :func:`find_pyproject`).

    Returns an empty config when no table is found. Raises :class:`ConfigError`
    on a wrong type, so a bad value can't silently turn the policy off. Unknown
    keys are listed in ``unknown_keys`` for the caller to warn about.
    """
    found = find_pyproject(start)
    if found is None:
        return EvalcraftConfig()
    path, data = found
    table = data["tool"]["evalcraft"]
    if not isinstance(table, dict):
        raise ConfigError(f"{path}: [tool.evalcraft] must be a table")

    cfg = EvalcraftConfig(source=path, unknown_keys=sorted(set(table) - set(KNOWN_KEYS)))
    base = path.parent
    for key in ("expire_after_days", "max_age_days"):
        if key in table:
            setattr(cfg, key, _positive_int(key, table[key], path))
    if "models" in table:
        models = table["models"]
        if isinstance(models, str):
            models = [m.strip() for m in models.split(",") if m.strip()]
        if (
            not isinstance(models, list)
            or not models
            or not all(isinstance(m, str) and m for m in models)
        ):
            raise ConfigError(
                f"{path}: [tool.evalcraft] models must be a non-empty list of model ids"
            )
        cfg.models = models
    for key in ("tools", "prompts"):
        if key in table:
            value = table[key]
            if not isinstance(value, str) or not value:
                raise ConfigError(f"{path}: [tool.evalcraft] {key} must be a file path")
            setattr(cfg, key, base / value)
    return cfg


def unknown_keys_message(cfg: EvalcraftConfig) -> str | None:
    """A warning for unknown keys in ``cfg``, or ``None``."""
    if not cfg.unknown_keys:
        return None
    return (
        f"{cfg.source}: ignoring unknown [tool.evalcraft] key(s) {cfg.unknown_keys}; "
        f"known keys: {list(KNOWN_KEYS)}"
    )

"""Field-level differences between the tool calls of two recordings.

Two runs can call the same tools in the same order, end with the same answer,
cost the same, and still differ in the one way that matters: the agent looked
up ``ORDER-999`` instead of ``ORDER-123``. This module pairs up the tool calls
of two cassettes and reports every argument and result field that changed.

Calls are paired per tool name in order (the 2nd ``lookup_order`` of the old
run with the 2nd of the new run). Argument changes are contract changes: the
agent asked for something different. Result changes are informational: they
come from the world the tool talked to. A value that is a run-time timestamp,
UUID or temp path on both sides is informational too, and ``ignore`` patterns
drop fields entirely.
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from evalcraft.core.models import Cassette

CONTRACT = "contract"
INFO = "info"
_MISSING = object()


@dataclass(frozen=True)
class ToolFieldChange:
    """One changed field of one tool call."""

    tool: str
    call: int          # 1-based occurrence of this tool in the run
    field: str         # e.g. "arguments.order_id" or "result.items[0].price"
    old: Any
    new: Any
    severity: str      # "contract" or "info"

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool, "call": self.call, "field": self.field,
            "old": None if self.old is _MISSING else self.old,
            "new": None if self.new is _MISSING else self.new,
            "old_missing": self.old is _MISSING, "new_missing": self.new is _MISSING,
            "severity": self.severity,
        }

    @property
    def label(self) -> str:
        if self.severity == CONTRACT:
            return "Tool contract changed"
        if self.field.startswith("arguments"):
            return "Tool argument changed (run-time value)"
        return "Tool result changed"

    def describe(self) -> str:
        def show(v: Any) -> str:
            return "(missing)" if v is _MISSING else json.dumps(v, default=str)
        return f"{self.field}: {show(self.old)} → {show(self.new)}"


def _parse(value: Any) -> Any:
    """Tool results are often JSON strings; compare their structure, not their text."""
    if isinstance(value, str):
        text = value.strip()
        if text[:1] in ("{", "["):
            try:
                return json.loads(text)
            except ValueError:
                return value
    return value


def _flatten(value: Any, prefix: str) -> dict[str, Any]:
    if isinstance(value, dict):
        if not value:
            return {prefix: {}}
        out: dict[str, Any] = {}
        for key in sorted(value, key=str):
            out.update(_flatten(value[key], f"{prefix}.{key}"))
        return out
    if isinstance(value, (list, tuple)):
        if not value:
            return {prefix: []}
        out = {}
        for index, item in enumerate(value):
            out.update(_flatten(item, f"{prefix}[{index}]"))
        return out
    return {prefix: value}


def _volatile(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    from evalcraft.staleness.volatile import VOLATILE_PATTERNS

    return any(p.fullmatch(value) for p in VOLATILE_PATTERNS.values())


def glob_match(pattern: str, text: str) -> bool:
    """Glob match where only ``*`` and ``?`` are wildcards.

    Field paths contain list indices (``messages[1].content``), which
    :mod:`fnmatch` would read as character classes.
    """
    regex = re.escape(pattern).replace(r"\*", ".*").replace(r"\?", ".")
    return re.fullmatch(regex, text) is not None


def _ignored(tool: str, field: str, patterns: Iterable[str]) -> bool:
    qualified = f"{tool}.{field}"
    return any(glob_match(p, qualified) or glob_match(p, field) for p in patterns)


def diff_tool_calls(
    old: Cassette,
    new: Cassette,
    *,
    ignore: Iterable[str] = (),
    compare_results: bool = True,
) -> list[ToolFieldChange]:
    """Every argument (and result) field that differs between paired tool calls.

    ``ignore`` takes glob patterns matched against ``<tool>.<field>`` or just
    ``<field>``: ``"*.arguments.request_id"``, ``"search.result.*"``,
    ``"arguments.timestamp"``. Calls with no counterpart (the tool ran more or
    fewer times) are not reported here; the tool sequence diff covers them.
    """
    patterns = tuple(ignore)
    by_tool_old: dict[str, list[Any]] = {}
    by_tool_new: dict[str, list[Any]] = {}
    for cassette, bucket in ((old, by_tool_old), (new, by_tool_new)):
        for span in cassette.get_tool_calls():
            if span.tool_name:
                bucket.setdefault(span.tool_name, []).append(span)

    changes: list[ToolFieldChange] = []
    for tool in sorted(set(by_tool_old) & set(by_tool_new)):
        pairs = zip(by_tool_old[tool], by_tool_new[tool], strict=False)
        for index, (a, b) in enumerate(pairs, start=1):
            parts = [("arguments", a.tool_args, b.tool_args, CONTRACT)]
            if compare_results:
                parts.append(("result", a.tool_result, b.tool_result, INFO))
            for root, va, vb, severity in parts:
                fa = _flatten(_parse(va) if va is not None else {}, root)
                fb = _flatten(_parse(vb) if vb is not None else {}, root)
                for field in sorted(set(fa) | set(fb)):
                    x, y = fa.get(field, _MISSING), fb.get(field, _MISSING)
                    if x == y or _ignored(tool, field, patterns):
                        continue
                    level = INFO if _volatile(x) and _volatile(y) else severity
                    changes.append(ToolFieldChange(tool, index, field, x, y, level))
    return changes

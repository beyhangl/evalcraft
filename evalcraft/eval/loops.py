"""Deterministic loop / repetition detection — catch agents stuck in a loop.

A stuck agent burns tokens repeating itself: calling the same tool with the same
arguments over and over, or emitting the same step output again and again. This
module flags both signals **offline, deterministically, and `$0`** — it reads
only the recorded spans and never calls a model or the network.

    from evalcraft import replay, assert_no_loops, assert_no_repeated_tool_calls

    run = replay("tests/cassettes/agent.json")
    assert assert_no_loops(run).passed
    assert assert_no_repeated_tool_calls(run, max_repeats=3).passed

Two signals:

- **Repeated tool calls** — the same ``(tool_name, tool_args)`` recorded more
  than ``max_repeats`` times (a retry loop / oscillation).
- **Repeated step outputs** — the same (or, with ``similarity < 1.0``, a
  near-duplicate by token overlap) LLM/agent-step output recorded more than
  ``max_repeats`` times.

``max_repeats`` is the maximum number of times a call/output may appear before
it is flagged: with the default of ``2``, a 3rd identical occurrence trips it.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from evalcraft.core.models import AgentRun, AssertionResult, Cassette, SpanKind
from evalcraft.eval._utils import get_cassette

# ──────────────────────────────────────────────
# Data classes
# ──────────────────────────────────────────────

@dataclass
class LoopFinding:
    """A single detected repetition."""
    kind: str          # "repeated_tool_call" | "repeated_output"
    signature: str     # human-readable description of what repeated
    count: int         # how many times it occurred
    max_allowed: int   # the threshold it exceeded

    def to_dict(self) -> dict:
        return {
            "kind": self.kind,
            "signature": self.signature,
            "count": self.count,
            "max_allowed": self.max_allowed,
        }


@dataclass
class LoopReport:
    """All repetitions detected in a run."""
    findings: list[LoopFinding] = field(default_factory=list)

    @property
    def has_loops(self) -> bool:
        return bool(self.findings)

    def to_dict(self) -> dict:
        return {
            "has_loops": self.has_loops,
            "findings": [f.to_dict() for f in self.findings],
        }


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def _trunc(text: str, n: int = 80) -> str:
    text = " ".join(text.split())
    return text if len(text) <= n else text[: n - 1] + "…"


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _norm(text: str) -> str:
    return " ".join(text.split())


def _jaccard(a: str, b: str) -> float:
    ta, tb = _tokens(a), _tokens(b)
    if not ta and not tb:
        # Neither has word tokens (e.g. punctuation/emoji-only outputs) — only
        # "similar" if textually identical, so distinct symbol-only outputs are
        # never falsely merged.
        return 1.0 if _norm(a) == _norm(b) else 0.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)


def _step_outputs(c: Cassette) -> list[tuple[str, str]]:
    """``(span_name, output)`` for each LLM-response / agent-step span, in order.

    Keyed by span name: a single answer echoed under several lifecycle spans
    (e.g. a framework's step, its task, and the crew/run result all carry the
    same final text under *different* names) is then counted once per name
    rather than as a false repetition loop. Genuine repetition reuses the same
    name (``llm:<model>``, a repeated step), so real loops are still caught.
    """
    return [
        (s.name or "", s.output)
        for s in c.spans
        if s.kind in (SpanKind.LLM_RESPONSE, SpanKind.AGENT_STEP) and s.output is not None
    ]


def _repeated_tool_calls(c: Cassette, max_repeats: int) -> list[LoopFinding]:
    counts: dict[tuple[str, str], int] = {}
    order: list[tuple[str, str]] = []
    for s in c.get_tool_calls():
        # Canonicalize args order-insensitively. Non-JSON arg values fall back to
        # str(); in the rare case two distinct non-JSON values share a str() they
        # would compare equal here.
        key = (s.tool_name or "", json.dumps(s.tool_args or {}, sort_keys=True, default=str))
        if key not in counts:
            order.append(key)
        counts[key] = counts.get(key, 0) + 1
    findings = []
    for name, args in order:
        n = counts[(name, args)]
        if n > max_repeats:
            sig = _trunc(f"{name}({args})")
            findings.append(LoopFinding("repeated_tool_call", sig, n, max_repeats))
    return findings


def _repeated_outputs(c: Cassette, max_repeats: int, similarity: float) -> list[LoopFinding]:
    steps = _step_outputs(c)  # list of (name, output)
    findings = []
    if similarity >= 1.0:
        # Case-insensitive (.casefold()) so this matches the near-duplicate branch,
        # which lowercases via _tokens — "Done"/"done" are one loop in both modes.
        counts: dict[tuple[str, str], int] = {}
        order: list[tuple[str, str]] = []
        display: dict[tuple[str, str], str] = {}
        for name, out in steps:
            key = (name, _norm(out).casefold())
            if key not in counts:
                order.append(key)
                display[key] = _norm(out)
            counts[key] = counts.get(key, 0) + 1
        for key in order:
            n = counts[key]
            if n > max_repeats:
                sig = _trunc(display[key])
                findings.append(LoopFinding("repeated_output", sig, n, max_repeats))
    else:
        # Connected components over the "same name AND token-overlap ≥ similarity"
        # graph (single-linkage). This catches gradual-drift loops where each step
        # is similar to its neighbour but not to the first, and is invariant to the
        # order in which equal-content steps appear.
        n_steps = len(steps)
        parent = list(range(n_steps))

        def find(x: int) -> int:
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i in range(n_steps):
            for j in range(i + 1, n_steps):
                if steps[i][0] == steps[j][0] and _jaccard(steps[i][1], steps[j][1]) >= similarity:
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[max(ri, rj)] = min(ri, rj)  # lowest index becomes root

        groups: dict[int, list[int]] = {}
        for i in range(n_steps):
            groups.setdefault(find(i), []).append(i)
        for root in sorted(groups):
            members = groups[root]
            if len(members) > max_repeats:
                rep = _trunc(steps[members[0]][1])  # lowest-index member = deterministic
                findings.append(LoopFinding("repeated_output", rep, len(members), max_repeats))
    return findings


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def detect_loops(
    cassette: Cassette | AgentRun,
    *,
    max_tool_repeats: int = 2,
    max_step_repeats: int = 2,
    similarity: float = 1.0,
) -> LoopReport:
    """Detect repetition loops in a recorded run.

    Args:
        cassette: The cassette or agent run to inspect.
        max_tool_repeats: Max identical ``(tool, args)`` calls before flagging.
        max_step_repeats: Max identical/near-duplicate step outputs before flagging.
        similarity: Token-overlap (Jaccard) threshold in ``(0, 1]`` for treating
            two step outputs as the "same"; ``1.0`` means exact match only.
    """
    if not (0.0 < similarity <= 1.0):
        raise ValueError(f"similarity must be in (0.0, 1.0], got {similarity}")
    c = get_cassette(cassette)
    findings = _repeated_tool_calls(c, max_tool_repeats)
    findings += _repeated_outputs(c, max_step_repeats, similarity)
    return LoopReport(findings=findings)


def assert_no_loops(
    cassette: Cassette | AgentRun,
    *,
    max_tool_repeats: int = 2,
    max_step_repeats: int = 2,
    similarity: float = 1.0,
) -> AssertionResult:
    """Assert the agent did not get stuck in a repetition loop.

    Deterministic and `$0` — see :func:`detect_loops`.
    """
    report = detect_loops(
        cassette,
        max_tool_repeats=max_tool_repeats,
        max_step_repeats=max_step_repeats,
        similarity=similarity,
    )
    if not report.has_loops:
        return AssertionResult(name="assert_no_loops", passed=True, expected="no repetition loops")
    shown = report.findings[:3]
    detail = "; ".join(f"{f.kind} ×{f.count} (>{f.max_allowed}): {f.signature}" for f in shown)
    if len(report.findings) > 3:
        detail += f" … (+{len(report.findings) - 3} more)"
    return AssertionResult(
        name="assert_no_loops",
        passed=False,
        expected="no repetition loops",
        actual=[f.to_dict() for f in report.findings],
        message=f"Detected {len(report.findings)} loop signal(s): {detail}",
    )


def assert_no_repeated_tool_calls(
    cassette: Cassette | AgentRun,
    *,
    max_repeats: int = 2,
) -> AssertionResult:
    """Assert no identical ``(tool, args)`` call repeats more than ``max_repeats`` times."""
    c = get_cassette(cassette)
    findings = _repeated_tool_calls(c, max_repeats)
    if not findings:
        return AssertionResult(
            name="assert_no_repeated_tool_calls", passed=True, expected="no repeated tool calls"
        )
    detail = "; ".join(f"{f.signature} ×{f.count}" for f in findings[:3])
    return AssertionResult(
        name="assert_no_repeated_tool_calls",
        passed=False,
        expected=f"≤{max_repeats} identical calls",
        actual=[f.to_dict() for f in findings],
        message=f"Repeated tool call(s) over the limit of {max_repeats}: {detail}",
    )

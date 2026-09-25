"""StalenessChecker — detect when a committed cassette no longer mirrors reality.

A cassette records *provenance* at capture time (the model set, a prompt hash,
and a timestamp). Replaying it tests the recorded run deterministically — but a
green replay says nothing if the world has moved on: the model it was recorded
against may have been retired, or the prompt it used may have changed. Then the
test keeps "passing" against a reality that no longer exists.

``StalenessChecker`` compares a cassette's provenance against the *current*
model set / prompt and reports findings by severity:

- ``reasoning_state_missing`` (CRITICAL) — spans recorded from a reasoning model
  carry no opaque reasoning state, so replaying them is invalid (the provider
  requires the signed reasoning block verbatim).
- ``model_retired`` (CRITICAL) — a recorded model is absent from the current set
  (retired or swapped); the cassette may now exercise an API that errors live.
- ``prompt_drift`` (WARNING) — the current prompt hash differs from the recording.
- ``tool_drift`` (WARNING) — a tool definition changed since the recording; the
  sharpest case is parameters that changed while the description did not.
- ``volatile_content`` (WARNING) — a UUID, timestamp or temp path generated at
  run time was baked into what the agent sent, so the recording won't match a
  rerun byte for byte.
- ``model_alias_moved`` (WARNING, across cassettes) — the same requested model id
  was served by different snapshots in different recordings.
- ``floating_model_alias`` (INFO) — the recording asked for a floating alias
  rather than a pinned snapshot.
- ``age`` (INFO) — the recording is older than a threshold.
- ``no_provenance`` (INFO) — a legacy / hand-built cassette without provenance.

Pure comparison logic — no network, no new dependencies, NetworkGuard-safe.

Usage::

    from evalcraft.staleness import StalenessChecker

    report = StalenessChecker().check(cassette, current_models=["gpt-5.1"])
    assert not report.has_critical
"""

from __future__ import annotations

import json
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette, compute_prompt_hash
from evalcraft.core.reasoning import find_degraded_reasoning_spans
from evalcraft.core.tool_defs import diff_tool_definitions
from evalcraft.regression.detector import Severity
from evalcraft.staleness.volatile import find_volatile_values

_DAY_SECONDS = 86400


@dataclass
class StalenessFinding:
    """A single staleness signal for a cassette."""

    category: str  # e.g. "model_retired", "prompt_drift", "tool_drift", "age"
    severity: Severity
    message: str
    recorded_value: Any = None
    current_value: Any = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "recorded_value": self.recorded_value,
            "current_value": self.current_value,
            "metadata": self.metadata,
        }


@dataclass
class StalenessReport:
    """All staleness findings for one cassette."""

    cassette_name: str = ""
    findings: list[StalenessFinding] = field(default_factory=list)

    @property
    def has_findings(self) -> bool:
        return len(self.findings) > 0

    @property
    def has_critical(self) -> bool:
        """True if any finding would block CI (a retired/swapped model)."""
        return any(f.severity == Severity.CRITICAL for f in self.findings)

    @property
    def max_severity(self) -> Severity | None:
        if not self.findings:
            return None
        order = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
        return max(self.findings, key=lambda f: order[f.severity]).severity

    def to_dict(self) -> dict:
        return {
            "cassette_name": self.cassette_name,
            "has_findings": self.has_findings,
            "has_critical": self.has_critical,
            "finding_count": len(self.findings),
            "max_severity": self.max_severity.value if self.max_severity else None,
            "findings": [f.to_dict() for f in self.findings],
        }


class StalenessChecker:
    """Compare a cassette's recorded provenance against current model/prompt config."""

    def __init__(self, *, max_age_days: int | None = None) -> None:
        self.max_age_days = max_age_days

    def check(
        self,
        cassette: Cassette,
        *,
        current_models: list[str] | None = None,
        current_prompt_hash: str | None = None,
        current_tools: list[dict[str, str]] | None = None,
    ) -> StalenessReport:
        """Build a :class:`StalenessReport` for ``cassette``.

        Args:
            cassette: the cassette to check.
            current_models: the model set you ship today. Any recorded model not
                in this set yields a CRITICAL ``model_retired`` finding. Matching
                is exact and case-sensitive (a swap *should* fire). Omit to skip
                the model check.
            current_prompt_hash: the hash of your current prompts (see
                :func:`hash_prompts_file` / :func:`compute_prompt_hash`). A
                mismatch with the recorded hash yields a WARNING ``prompt_drift``.
                Omit to skip.
            current_tools: the tool definitions your code ships today, normalised
                with :func:`~evalcraft.core.tool_defs.normalize_tool_definitions`
                (or read with :func:`~evalcraft.core.tool_defs.load_tool_definitions`).
                Each difference from the recorded definitions yields a WARNING
                ``tool_drift``. Omit to skip.

        Volatile values in the recorded LLM inputs and tool arguments are always
        checked. Age is checked against ``max_age_days`` (set on the checker) using the
        provenance ``recorded_at`` timestamp. Never raises on missing/partial
        provenance — a cassette without provenance yields a single INFO
        ``no_provenance`` finding.
        """
        report = StalenessReport(cassette_name=cassette.name)

        # 0. Missing opaque reasoning state (CRITICAL — replay is *invalid*, not
        # merely lossy: the provider rejects or degrades a turn whose signed
        # reasoning block was dropped). Checked before provenance, because a
        # legacy cassette can be degraded this way too.
        degraded = find_degraded_reasoning_spans(cassette)
        if degraded:
            models = sorted({s.model for s in degraded if s.model})
            report.findings.append(
                StalenessFinding(
                    category="reasoning_state_missing",
                    severity=Severity.CRITICAL,
                    message=(
                        f"{len(degraded)} span(s) recorded from reasoning model(s) "
                        f"{models} carry no reasoning state. Replaying them is "
                        "invalid — the provider requires the signed reasoning "
                        "block verbatim. Re-record with an adapter that captures it."
                    ),
                    recorded_value=models,
                )
            )

        volatile = find_volatile_values(cassette)
        if volatile:
            shown = ", ".join(f"{v.kind} {v.value!r} ({v.where})" for v in volatile[:3])
            more = f" and {len(volatile) - 3} more" if len(volatile) > 3 else ""
            report.findings.append(
                StalenessFinding(
                    category="volatile_content",
                    severity=Severity.WARNING,
                    message=(
                        f"Run-time values were recorded in what the agent sent: "
                        f"{shown}{more}. A rerun sends different values, so "
                        "prompt-keyed mocks miss and re-recording churns the diff. "
                        "Inject a fixed clock, id factory or path in tests."
                    ),
                    recorded_value=[v.to_dict() for v in volatile],
                )
            )

        prov = cassette.provenance

        if prov is None:
            report.findings.append(
                StalenessFinding(
                    category="no_provenance",
                    severity=Severity.INFO,
                    message=(
                        "Cassette has no provenance — re-record it to enable "
                        "staleness checks (model / prompt / age)."
                    ),
                )
            )
            return report

        # 1. Retired / swapped models (CRITICAL — the cassette may now 4xx live).
        if current_models is not None:
            current_set = set(current_models)
            # Judge what the code asked for. A dated snapshot served for an alias
            # you still ship is not retired (floating_model_alias covers it), and
            # an alias is fine if every snapshot it was served as is still shipped.
            # Cassettes from before 0.9 only know the served models.
            for model in prov.requested_models or prov.models:
                served = prov.model_aliases.get(model, [])
                if served and all(m in current_set for m in served):
                    continue
                if model not in current_set:
                    report.findings.append(
                        StalenessFinding(
                            category="model_retired",
                            severity=Severity.CRITICAL,
                            message=(
                                f"Recorded model {model!r} is not in the current "
                                f"model set — it may have been retired or swapped. "
                                f"This deterministic test no longer mirrors production."
                            ),
                            recorded_value=model,
                            current_value=sorted(current_set),
                        )
                    )

        # 2. Prompt drift (WARNING — still replays, but no longer mirrors the prompt).
        if (
            current_prompt_hash is not None
            and prov.prompt_hash
            and current_prompt_hash != prov.prompt_hash
        ):
            report.findings.append(
                StalenessFinding(
                    category="prompt_drift",
                    severity=Severity.WARNING,
                    message=(
                        "Current prompt hash differs from the recorded one — "
                        "the cassette still replays but no longer reflects the "
                        "live prompt."
                    ),
                    recorded_value=prov.prompt_hash,
                    current_value=current_prompt_hash,
                )
            )

        # 3. Tool-definition drift (WARNING — the model now sees different tools).
        if current_tools is not None:
            if prov.tools:
                for kind, name, message in diff_tool_definitions(prov.tools, current_tools):
                    report.findings.append(
                        StalenessFinding(
                            category="tool_drift",
                            severity=Severity.WARNING,
                            message=message,
                            recorded_value=name,
                            metadata={"change": kind},
                        )
                    )
            else:
                report.findings.append(
                    StalenessFinding(
                        category="no_tool_definitions",
                        severity=Severity.INFO,
                        message=(
                            "Cassette has no recorded tool definitions. Either the "
                            "run offered no tools, or it was recorded before 0.9 or "
                            "through an adapter that doesn't record them (only the "
                            "OpenAI and Anthropic adapters do)."
                        ),
                    )
                )

        # 4. Floating model aliases (INFO — the id you call can change underneath you).
        for requested, served in sorted(prov.model_aliases.items()):
            report.findings.append(
                StalenessFinding(
                    category="floating_model_alias",
                    severity=Severity.INFO,
                    message=(
                        f"Requested {requested!r} but {', '.join(map(repr, served))} "
                        "answered. The alias can move to a new snapshot without "
                        "notice. Pin the snapshot to keep live runs comparable to "
                        "this recording."
                    ),
                    recorded_value=requested,
                    current_value=list(served),
                )
            )
        for model in prov.requested_models or prov.models:
            if "latest" in model.lower() and model not in prov.model_aliases:
                report.findings.append(
                    StalenessFinding(
                        category="floating_model_alias",
                        severity=Severity.INFO,
                        message=(
                            f"Recorded against {model!r}, a floating id. Pin a dated "
                            "snapshot to keep live runs comparable to this recording."
                        ),
                        recorded_value=model,
                    )
                )

        # 5. Age (INFO — weakest signal; upgrades doctor's mtime check to recorded_at).
        if self.max_age_days is not None and prov.recorded_at:
            age_days = (time.time() - prov.recorded_at) / _DAY_SECONDS
            if age_days > self.max_age_days:
                report.findings.append(
                    StalenessFinding(
                        category="age",
                        severity=Severity.INFO,
                        message=(
                            f"Recorded {age_days:.0f} days ago "
                            f"(threshold {self.max_age_days}) — consider re-recording."
                        ),
                        recorded_value=prov.recorded_at,
                        current_value=self.max_age_days,
                        metadata={"age_days": age_days},
                    )
                )

        return report


def find_alias_moves(cassettes: Iterable[tuple[str, Cassette]]) -> list[StalenessFinding]:
    """Flag requested model ids that different recordings saw served by different models.

    Takes ``(label, cassette)`` pairs. When ``gpt-4o`` resolved to one snapshot in
    one recording and another snapshot in a later one (or two snapshots within
    one recording), the model behind an
    unchanged id changed between recordings, so their behaviour is not directly
    comparable. One WARNING ``model_alias_moved`` is returned per such id.
    """
    seen: dict[str, dict[str, list[tuple[float, str]]]] = {}
    for label, cassette in cassettes:
        prov = cassette.provenance
        if prov is None:
            continue
        for requested, served_list in prov.model_aliases.items():
            for served in served_list:
                seen.setdefault(requested, {}).setdefault(served, []).append(
                    (prov.recorded_at, label)
                )
    findings: list[StalenessFinding] = []
    for requested in sorted(seen):
        served_map = seen[requested]
        if len(served_map) < 2:
            continue
        # Order snapshots by when they were first seen.
        ordered = sorted(served_map.items(), key=lambda kv: min(t for t, _ in kv[1]))
        parts = [
            f"{served!r} in {', '.join(sorted(lbl for _, lbl in uses))}"
            for served, uses in ordered
        ]
        findings.append(
            StalenessFinding(
                category="model_alias_moved",
                severity=Severity.WARNING,
                message=(
                    f"{requested!r} was served by different models across recordings: "
                    f"{'; '.join(parts)}. The model behind this id changed, so these "
                    "recordings are not directly comparable."
                ),
                recorded_value=requested,
                current_value=[served for served, _ in ordered],
                metadata={
                    "served": {served: sorted(lbl for _, lbl in uses) for served, uses in ordered}
                },
            )
        )
    return findings


def hash_prompts_file(path: str | Path) -> str:
    """Compute the prompt hash for a *current* prompts file, to compare with a recording.

    Accepts:

    - a JSON object with ``input_text`` and/or ``llm_inputs`` keys, or
    - a JSON list (treated as ``llm_inputs`` with empty ``input_text``), or
    - any other text (treated as ``input_text`` with no ``llm_inputs``).

    The hash basis is identical to
    :func:`evalcraft.core.models.compute_prompt_hash`, so a file matching the
    recording hashes to the recorded value byte-for-byte.
    """
    text = Path(path).read_text()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return compute_prompt_hash(text, [])

    if isinstance(data, dict):
        return compute_prompt_hash(
            str(data.get("input_text", "")),
            list(data.get("llm_inputs", [])),
        )
    if isinstance(data, list):
        return compute_prompt_hash("", data)
    # JSON scalar (string / number / bool) — treat as input_text.
    return compute_prompt_hash(str(data), [])

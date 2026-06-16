"""StalenessChecker — detect when a committed cassette no longer mirrors reality.

A cassette records *provenance* at capture time (the model set, a prompt hash,
and a timestamp). Replaying it tests the recorded run deterministically — but a
green replay says nothing if the world has moved on: the model it was recorded
against may have been retired, or the prompt it used may have changed. Then the
test keeps "passing" against a reality that no longer exists.

``StalenessChecker`` compares a cassette's provenance against the *current*
model set / prompt and reports findings by severity:

- ``model_retired`` (CRITICAL) — a recorded model is absent from the current set
  (retired or swapped); the cassette may now exercise an API that errors live.
- ``prompt_drift`` (WARNING) — the current prompt hash differs from the recording.
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
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette, compute_prompt_hash
from evalcraft.regression.detector import Severity

_DAY_SECONDS = 86400


@dataclass
class StalenessFinding:
    """A single staleness signal for a cassette."""

    category: str  # "model_retired" | "prompt_drift" | "age" | "no_provenance"
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

        Age is checked against ``max_age_days`` (set on the checker) using the
        provenance ``recorded_at`` timestamp. Never raises on missing/partial
        provenance — a cassette without provenance yields a single INFO
        ``no_provenance`` finding.
        """
        report = StalenessReport(cassette_name=cassette.name)
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
            for model in prov.models:
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

        # 3. Age (INFO — weakest signal; upgrades doctor's mtime check to recorded_at).
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

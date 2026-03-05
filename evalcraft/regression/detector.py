"""RegressionDetector — detect behavioral drift between agent runs.

Compares a new cassette against a golden baseline and produces a report
of regressions with severity levels.

Usage:
    from evalcraft.regression import RegressionDetector

    detector = RegressionDetector()
    report = detector.compare(golden_cassette, new_cassette)
    print(report.summary())
    assert not report.has_critical
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette, SpanKind


class Severity(str, Enum):
    """Severity level for a detected regression."""
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


@dataclass
class Regression:
    """A single detected regression."""
    category: str
    severity: Severity
    message: str
    golden_value: Any = None
    current_value: Any = None
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "severity": self.severity.value,
            "message": self.message,
            "golden_value": self.golden_value,
            "current_value": self.current_value,
            "metadata": self.metadata,
        }


@dataclass
class RegressionReport:
    """Report of all regressions found in a comparison."""
    golden_name: str = ""
    regressions: list[Regression] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def has_regressions(self) -> bool:
        return len(self.regressions) > 0

    @property
    def has_critical(self) -> bool:
        return any(r.severity == Severity.CRITICAL for r in self.regressions)

    @property
    def has_warnings(self) -> bool:
        return any(r.severity == Severity.WARNING for r in self.regressions)

    @property
    def max_severity(self) -> Severity | None:
        if not self.regressions:
            return None
        order = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
        return max(self.regressions, key=lambda r: order[r.severity]).severity

    def by_severity(self, severity: Severity) -> list[Regression]:
        return [r for r in self.regressions if r.severity == severity]

    def to_dict(self) -> dict:
        return {
            "golden_name": self.golden_name,
            "has_regressions": self.has_regressions,
            "has_critical": self.has_critical,
            "regression_count": len(self.regressions),
            "max_severity": self.max_severity.value if self.max_severity else None,
            "regressions": [r.to_dict() for r in self.regressions],
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        """Human-readable summary of the regression report."""
        if not self.regressions:
            return f"No regressions detected against '{self.golden_name}'."

        lines = [
            f"Regression report for '{self.golden_name}':",
            f"  {len(self.regressions)} regression(s) found",
        ]

        for sev in (Severity.CRITICAL, Severity.WARNING, Severity.INFO):
            items = self.by_severity(sev)
            if items:
                lines.append(f"\n  {sev.value}:")
                for r in items:
                    lines.append(f"    - [{r.category}] {r.message}")

        return "\n".join(lines)


class RegressionDetector:
    """Detect regressions by comparing a new cassette against a golden baseline.

    Checks for:
    - Tool sequence changes (order, additions, removals)
    - Output drift (text changed)
    - Cost increase
    - Latency increase
    - Token bloat
    - LLM call count changes
    - Tool call count changes
    - Error introduction
    """

    def __init__(
        self,
        *,
        cost_warning_ratio: float = 1.2,
        cost_critical_ratio: float = 2.0,
        latency_warning_ratio: float = 1.5,
        latency_critical_ratio: float = 3.0,
        token_warning_ratio: float = 1.3,
        token_critical_ratio: float = 2.0,
    ):
        self.cost_warning_ratio = cost_warning_ratio
        self.cost_critical_ratio = cost_critical_ratio
        self.latency_warning_ratio = latency_warning_ratio
        self.latency_critical_ratio = latency_critical_ratio
        self.token_warning_ratio = token_warning_ratio
        self.token_critical_ratio = token_critical_ratio

    def compare(
        self,
        golden: Cassette,
        current: Cassette,
    ) -> RegressionReport:
        """Compare a current cassette against a golden baseline."""
        golden.compute_metrics()
        current.compute_metrics()

        report = RegressionReport(golden_name=golden.name)
        regressions: list[Regression] = []

        regressions.extend(self._check_tool_sequence(golden, current))
        regressions.extend(self._check_output(golden, current))
        regressions.extend(self._check_tokens(golden, current))
        regressions.extend(self._check_cost(golden, current))
        regressions.extend(self._check_latency(golden, current))
        regressions.extend(self._check_call_counts(golden, current))
        regressions.extend(self._check_errors(golden, current))

        report.regressions = regressions
        return report

    def check_directory(
        self,
        golden_dir: str | Path,
        current_dir: str | Path,
    ) -> list[RegressionReport]:
        """Compare all cassettes in a directory against golden baselines.

        Matches cassettes by filename.
        """
        golden_dir = Path(golden_dir)
        current_dir = Path(current_dir)
        reports = []

        for current_file in sorted(current_dir.glob("*.json")):
            golden_file = golden_dir / current_file.name
            if not golden_file.exists():
                # New cassette — no baseline to compare
                report = RegressionReport(golden_name=current_file.stem)
                report.regressions.append(Regression(
                    category="new_cassette",
                    severity=Severity.INFO,
                    message=f"No golden baseline found for {current_file.name}",
                ))
                reports.append(report)
                continue

            try:
                golden = Cassette.load(golden_file)
                current = Cassette.load(current_file)
                reports.append(self.compare(golden, current))
            except Exception as e:
                report = RegressionReport(golden_name=current_file.stem)
                report.regressions.append(Regression(
                    category="load_error",
                    severity=Severity.WARNING,
                    message=f"Error loading cassettes: {e}",
                ))
                reports.append(report)

        return reports

    # ──────────────────────────────────────────
    # Check methods
    # ──────────────────────────────────────────

    def _check_tool_sequence(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        golden_seq = golden.get_tool_sequence()
        current_seq = current.get_tool_sequence()

        if golden_seq == current_seq:
            return []

        regressions = []

        # Check for removed tools
        golden_set = set(golden_seq)
        current_set = set(current_seq)
        removed = golden_set - current_set
        added = current_set - golden_set

        if removed:
            regressions.append(Regression(
                category="tool_sequence",
                severity=Severity.CRITICAL,
                message=f"Tools removed from sequence: {sorted(removed)}",
                golden_value=golden_seq,
                current_value=current_seq,
            ))

        if added:
            regressions.append(Regression(
                category="tool_sequence",
                severity=Severity.WARNING,
                message=f"New tools added to sequence: {sorted(added)}",
                golden_value=golden_seq,
                current_value=current_seq,
            ))

        # Check order change (same tools, different order)
        if not removed and not added and golden_seq != current_seq:
            regressions.append(Regression(
                category="tool_sequence",
                severity=Severity.WARNING,
                message=f"Tool execution order changed",
                golden_value=golden_seq,
                current_value=current_seq,
            ))

        return regressions

    def _check_output(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        if golden.output_text == current.output_text:
            return []

        # Empty output when golden had output is critical
        if golden.output_text and not current.output_text:
            return [Regression(
                category="output_drift",
                severity=Severity.CRITICAL,
                message="Agent produced no output (golden had output)",
                golden_value=golden.output_text[:200],
                current_value="(empty)",
            )]

        return [Regression(
            category="output_drift",
            severity=Severity.INFO,
            message="Output text differs from golden baseline",
            golden_value=golden.output_text[:200],
            current_value=current.output_text[:200],
        )]

    def _check_tokens(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        if golden.total_tokens == 0:
            return []

        ratio = current.total_tokens / golden.total_tokens

        if ratio >= self.token_critical_ratio:
            return [Regression(
                category="token_bloat",
                severity=Severity.CRITICAL,
                message=(
                    f"Token usage increased {ratio:.2f}x "
                    f"({golden.total_tokens} -> {current.total_tokens})"
                ),
                golden_value=golden.total_tokens,
                current_value=current.total_tokens,
                metadata={"ratio": ratio},
            )]

        if ratio >= self.token_warning_ratio:
            return [Regression(
                category="token_bloat",
                severity=Severity.WARNING,
                message=(
                    f"Token usage increased {ratio:.2f}x "
                    f"({golden.total_tokens} -> {current.total_tokens})"
                ),
                golden_value=golden.total_tokens,
                current_value=current.total_tokens,
                metadata={"ratio": ratio},
            )]

        return []

    def _check_cost(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        if golden.total_cost_usd == 0:
            return []

        ratio = current.total_cost_usd / golden.total_cost_usd

        if ratio >= self.cost_critical_ratio:
            return [Regression(
                category="cost_increase",
                severity=Severity.CRITICAL,
                message=(
                    f"Cost increased {ratio:.2f}x "
                    f"(${golden.total_cost_usd:.4f} -> ${current.total_cost_usd:.4f})"
                ),
                golden_value=golden.total_cost_usd,
                current_value=current.total_cost_usd,
                metadata={"ratio": ratio},
            )]

        if ratio >= self.cost_warning_ratio:
            return [Regression(
                category="cost_increase",
                severity=Severity.WARNING,
                message=(
                    f"Cost increased {ratio:.2f}x "
                    f"(${golden.total_cost_usd:.4f} -> ${current.total_cost_usd:.4f})"
                ),
                golden_value=golden.total_cost_usd,
                current_value=current.total_cost_usd,
                metadata={"ratio": ratio},
            )]

        return []

    def _check_latency(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        if golden.total_duration_ms == 0:
            return []

        ratio = current.total_duration_ms / golden.total_duration_ms

        if ratio >= self.latency_critical_ratio:
            return [Regression(
                category="latency_increase",
                severity=Severity.CRITICAL,
                message=(
                    f"Latency increased {ratio:.2f}x "
                    f"({golden.total_duration_ms:.0f}ms -> {current.total_duration_ms:.0f}ms)"
                ),
                golden_value=golden.total_duration_ms,
                current_value=current.total_duration_ms,
                metadata={"ratio": ratio},
            )]

        if ratio >= self.latency_warning_ratio:
            return [Regression(
                category="latency_increase",
                severity=Severity.WARNING,
                message=(
                    f"Latency increased {ratio:.2f}x "
                    f"({golden.total_duration_ms:.0f}ms -> {current.total_duration_ms:.0f}ms)"
                ),
                golden_value=golden.total_duration_ms,
                current_value=current.total_duration_ms,
                metadata={"ratio": ratio},
            )]

        return []

    def _check_call_counts(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        regressions = []

        if current.llm_call_count > golden.llm_call_count and golden.llm_call_count > 0:
            ratio = current.llm_call_count / golden.llm_call_count
            severity = Severity.WARNING if ratio < 2.0 else Severity.CRITICAL
            regressions.append(Regression(
                category="llm_call_count",
                severity=severity,
                message=(
                    f"LLM calls increased "
                    f"({golden.llm_call_count} -> {current.llm_call_count})"
                ),
                golden_value=golden.llm_call_count,
                current_value=current.llm_call_count,
            ))

        if current.tool_call_count > golden.tool_call_count and golden.tool_call_count > 0:
            ratio = current.tool_call_count / golden.tool_call_count
            severity = Severity.WARNING if ratio < 2.0 else Severity.CRITICAL
            regressions.append(Regression(
                category="tool_call_count",
                severity=severity,
                message=(
                    f"Tool calls increased "
                    f"({golden.tool_call_count} -> {current.tool_call_count})"
                ),
                golden_value=golden.tool_call_count,
                current_value=current.tool_call_count,
            ))

        return regressions

    def _check_errors(
        self, golden: Cassette, current: Cassette
    ) -> list[Regression]:
        golden_errors = [s for s in golden.spans if s.error]
        current_errors = [s for s in current.spans if s.error]

        new_error_count = len(current_errors) - len(golden_errors)
        if new_error_count > 0:
            error_msgs = [s.error for s in current_errors[:3]]
            return [Regression(
                category="new_errors",
                severity=Severity.CRITICAL,
                message=(
                    f"{new_error_count} new error(s) introduced: "
                    f"{error_msgs}"
                ),
                golden_value=len(golden_errors),
                current_value=len(current_errors),
            )]

        return []

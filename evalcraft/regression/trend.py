"""TrendDetector — detect gradual behavioral drift across multiple agent runs.

Unlike RegressionDetector (pairwise: golden vs current), TrendDetector
analyzes an ordered sequence of cassettes to find monotonic or accelerating
drift invisible to single-comparison metrics.

Usage::

    from evalcraft.regression import TrendDetector

    cassettes = [run1, run2, run3, run4, run5]  # ordered oldest→newest
    detector = TrendDetector(window_size=5, slope_warning_pct=0.05)
    report = detector.detect(cassettes)

    if report.has_drift:
        print(report.summary())
    assert not report.has_critical_drift
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Sequence

from evalcraft.core.models import Cassette
from evalcraft.regression.detector import Severity


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class TrendRegression:
    """A single detected trend regression across N runs.

    Attributes
    ----------
    category:
        Metric name: ``"cost_usd"``, ``"duration_ms"``, ``"llm_calls"``,
        ``"tool_calls"``, or ``"error_count"``.
    slope_per_run:
        Average absolute change per run (raw units of the metric).
    slope_pct:
        Average *percentage* change per run relative to the window mean.
    severity:
        ``INFO`` | ``WARNING`` | ``CRITICAL``.
    window_start:
        Name of the oldest cassette in the analysis window.
    window_end:
        Name of the newest cassette in the analysis window.
    run_count:
        Number of runs used to compute this trend.
    values:
        Raw metric values per run (oldest → newest) for downstream
        visualisation or further analysis.
    message:
        Human-readable description of the detected trend.
    """

    category: str
    slope_per_run: float
    slope_pct: float
    severity: Severity
    window_start: str
    window_end: str
    run_count: int
    values: list[float]
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "slope_per_run": self.slope_per_run,
            "slope_pct": self.slope_pct,
            "severity": self.severity.value,
            "window_start": self.window_start,
            "window_end": self.window_end,
            "run_count": self.run_count,
            "values": self.values,
            "message": self.message,
        }


@dataclass
class TrendReport:
    """Aggregated result of a multi-run trend analysis.

    Attributes
    ----------
    run_count:
        Number of cassettes analysed.
    cassette_names:
        Names of all cassettes in the analysis window (oldest → newest).
    trends:
        All detected trend regressions.
    """

    run_count: int
    cassette_names: list[str]
    trends: list[TrendRegression] = field(default_factory=list)

    # ------------------------------------------------------------------
    # Convenience properties
    # ------------------------------------------------------------------

    @property
    def has_drift(self) -> bool:
        """True if any trend regression was detected."""
        return len(self.trends) > 0

    @property
    def has_critical_drift(self) -> bool:
        """True if any trend is at CRITICAL severity."""
        return any(t.severity == Severity.CRITICAL for t in self.trends)

    @property
    def has_warning_drift(self) -> bool:
        """True if any trend is at WARNING severity."""
        return any(t.severity == Severity.WARNING for t in self.trends)

    @property
    def max_severity(self) -> Severity | None:
        """Highest severity among detected trends, or ``None`` if none."""
        if not self.trends:
            return None
        order = {Severity.INFO: 0, Severity.WARNING: 1, Severity.CRITICAL: 2}
        return max(self.trends, key=lambda t: order[t.severity]).severity

    def by_severity(self, severity: Severity) -> list[TrendRegression]:
        """Filter trends by severity."""
        return [t for t in self.trends if t.severity == severity]

    # ------------------------------------------------------------------
    # Serialisation
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "run_count": self.run_count,
            "cassette_names": self.cassette_names,
            "has_drift": self.has_drift,
            "has_critical_drift": self.has_critical_drift,
            "trend_count": len(self.trends),
            "max_severity": self.max_severity.value if self.max_severity else None,
            "trends": [t.to_dict() for t in self.trends],
        }

    def summary(self) -> str:
        """Human-readable summary of the trend report."""
        if not self.trends:
            return (
                f"No drift detected across {self.run_count} runs "
                f"({self.cassette_names[0]} … {self.cassette_names[-1]})."
            )
        lines = [
            f"Drift detected across {self.run_count} runs "
            f"({self.cassette_names[0]} … {self.cassette_names[-1]}):",
            f"  {len(self.trends)} trend regression(s) found:",
        ]
        for t in self.trends:
            lines.append(
                f"  [{t.severity.value}] {t.category}: "
                f"{t.slope_pct:+.1%}/run over {t.run_count} runs"
            )
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# TrendDetector
# ---------------------------------------------------------------------------


class TrendDetector:
    """Detect gradual behavioral drift across an ordered sequence of cassettes.

    Parameters
    ----------
    window_size:
        Maximum number of recent cassettes to include in the analysis.
        If the supplied list is shorter, all cassettes are used.
        Minimum effective window is 3 (two windows of fewer cassettes
        produce unreliable slopes and are skipped).
    slope_warning_pct:
        Average *percentage* change per run that triggers a WARNING.
        Default ``0.05`` (5 % / run).
    slope_critical_pct:
        Average percentage change per run that triggers a CRITICAL.
        Default ``0.15`` (15 % / run).
    min_baseline:
        Minimum absolute value a metric must have in the first run before
        percentage-slope calculations are performed.  Prevents division by
        near-zero from inflating percentages for idle agents.
        Default ``1e-6``.

    Notes
    -----
    Slopes are computed with simple linear regression (least-squares fit)
    over the ordered values, which is more robust than comparing only the
    first and last run when intermediate values fluctuate.
    """

    def __init__(
        self,
        window_size: int = 5,
        slope_warning_pct: float = 0.05,
        slope_critical_pct: float = 0.15,
        min_baseline: float = 1e-6,
    ) -> None:
        if window_size < 2:
            raise ValueError("window_size must be at least 2")
        self.window_size = window_size
        self.slope_warning_pct = slope_warning_pct
        self.slope_critical_pct = slope_critical_pct
        self.min_baseline = min_baseline

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def detect(self, cassettes: Sequence[Cassette]) -> TrendReport:
        """Analyse an ordered sequence of cassettes for gradual drift.

        Parameters
        ----------
        cassettes:
            Agent run cassettes ordered **oldest → newest**.  At least 3
            cassettes are required; fewer returns an empty report.

        Returns
        -------
        TrendReport
            Contains all detected :class:`TrendRegression` instances.
        """
        window = list(cassettes)[-self.window_size :]
        names = [c.name for c in window]

        report = TrendReport(run_count=len(window), cassette_names=names)

        if len(window) < 3:
            return report  # not enough data for reliable slope

        metrics: list[tuple[str, list[float]]] = [
            ("cost_usd", [c.total_cost_usd for c in window]),
            ("duration_ms", [c.total_duration_ms for c in window]),
            ("llm_calls", [float(c.llm_call_count) for c in window]),
            ("tool_calls", [float(c.tool_call_count) for c in window]),
            ("error_count", [float(sum(1 for s in c.spans if s.error)) for c in window]),
        ]

        for category, values in metrics:
            trend = self._analyse_metric(category, values, names)
            if trend is not None:
                report.trends.append(trend)

        return report

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _analyse_metric(
        self,
        category: str,
        values: list[float],
        names: list[str],
    ) -> TrendRegression | None:
        """Run linear regression on *values* and return a TrendRegression
        if the slope exceeds the configured thresholds, else ``None``."""
        n = len(values)
        mean_val = sum(values) / n

        # Skip metrics that are effectively zero (e.g. no cost measured)
        if mean_val < self.min_baseline:
            return None

        slope = self._linear_slope(values)

        # Express slope as a fraction of the window mean so it's comparable
        # across metrics with different absolute magnitudes.
        slope_pct = slope / mean_val  # signed: positive = growing

        # Only flag *increasing* trends (degradation direction).
        if slope_pct <= 0:
            return None

        if slope_pct >= self.slope_critical_pct:
            severity = Severity.CRITICAL
        elif slope_pct >= self.slope_warning_pct:
            severity = Severity.WARNING
        else:
            return None  # below INFO threshold

        message = (
            f"{category} increasing at {slope_pct:+.1%}/run on average "
            f"over {n} runs "
            f"({values[0]:.4g} → {values[-1]:.4g})"
        )

        return TrendRegression(
            category=category,
            slope_per_run=slope,
            slope_pct=slope_pct,
            severity=severity,
            window_start=names[0],
            window_end=names[-1],
            run_count=n,
            values=values,
            message=message,
        )

    @staticmethod
    def _linear_slope(values: list[float]) -> float:
        """Compute the least-squares slope of *values* vs. run index.

        Returns the change in the metric *per run* (positive = increasing).
        Uses only the standard library; no NumPy required.
        """
        n = len(values)
        xs = list(range(n))
        mean_x = sum(xs) / n
        mean_y = sum(values) / n

        num = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, values))
        den = sum((x - mean_x) ** 2 for x in xs)

        return num / den if den != 0 else 0.0

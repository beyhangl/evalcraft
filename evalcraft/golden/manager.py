"""GoldenSet — a versioned collection of cassettes representing expected agent behavior.

A golden set is the "known-good" baseline that new agent runs are compared
against.  It stores one or more cassettes along with version metadata, and
provides diffing / pass-fail determination with configurable thresholds.

Usage:
    from evalcraft.golden import GoldenSet

    # Create and save
    gs = GoldenSet(name="weather_agent_v1")
    gs.add_cassette(cassette)
    gs.save("golden/weather_agent.golden.json")

    # Load and compare
    gs = GoldenSet.load("golden/weather_agent.golden.json")
    result = gs.compare(new_cassette)
    assert result.passed
"""

from __future__ import annotations

import copy
import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from evalcraft.core.models import Cassette


# ──────────────────────────────────────────────
# Comparison result
# ──────────────────────────────────────────────

@dataclass
class ComparisonField:
    """Result of comparing a single field between golden and candidate."""
    name: str
    passed: bool
    golden_value: Any = None
    candidate_value: Any = None
    message: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "golden_value": self.golden_value,
            "candidate_value": self.candidate_value,
            "message": self.message,
        }


@dataclass
class ComparisonResult:
    """Result of comparing a cassette against a golden set."""
    passed: bool = True
    golden_name: str = ""
    golden_version: int = 0
    fields: list[ComparisonField] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def failed_fields(self) -> list[ComparisonField]:
        return [f for f in self.fields if not f.passed]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "golden_name": self.golden_name,
            "golden_version": self.golden_version,
            "fields": [f.to_dict() for f in self.fields],
            "metadata": self.metadata,
        }

    def summary(self) -> str:
        """Human-readable summary."""
        lines = [
            f"Golden set: {self.golden_name} (v{self.golden_version})",
            f"Result: {'PASS' if self.passed else 'FAIL'}",
        ]
        for f in self.fields:
            icon = "PASS" if f.passed else "FAIL"
            lines.append(f"  [{icon}] {f.name}")
            if not f.passed and f.message:
                lines.append(f"         {f.message}")
        return "\n".join(lines)


# ──────────────────────────────────────────────
# Thresholds
# ──────────────────────────────────────────────

@dataclass
class Thresholds:
    """Configurable thresholds for golden-set comparison.

    Each threshold controls what constitutes a "pass" for that dimension.
    Set to None to skip checking that dimension.
    """
    # Tool sequence must match exactly
    tool_sequence_must_match: bool = True

    # Output text must match exactly
    output_must_match: bool = False

    # Max allowable increase ratios (1.0 = no increase allowed)
    max_token_increase_ratio: float | None = 1.5
    max_cost_increase_ratio: float | None = 2.0
    max_latency_increase_ratio: float | None = 3.0

    # Absolute limits (applied regardless of golden values)
    max_tokens: int | None = None
    max_cost_usd: float | None = None
    max_latency_ms: float | None = None

    def to_dict(self) -> dict:
        return {
            "tool_sequence_must_match": self.tool_sequence_must_match,
            "output_must_match": self.output_must_match,
            "max_token_increase_ratio": self.max_token_increase_ratio,
            "max_cost_increase_ratio": self.max_cost_increase_ratio,
            "max_latency_increase_ratio": self.max_latency_increase_ratio,
            "max_tokens": self.max_tokens,
            "max_cost_usd": self.max_cost_usd,
            "max_latency_ms": self.max_latency_ms,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Thresholds:
        return cls(
            tool_sequence_must_match=data.get("tool_sequence_must_match", True),
            output_must_match=data.get("output_must_match", False),
            max_token_increase_ratio=data.get("max_token_increase_ratio", 1.5),
            max_cost_increase_ratio=data.get("max_cost_increase_ratio", 2.0),
            max_latency_increase_ratio=data.get("max_latency_increase_ratio", 3.0),
            max_tokens=data.get("max_tokens"),
            max_cost_usd=data.get("max_cost_usd"),
            max_latency_ms=data.get("max_latency_ms"),
        )


# ──────────────────────────────────────────────
# GoldenSet
# ──────────────────────────────────────────────

class GoldenSet:
    """A versioned collection of cassettes representing expected agent behavior.

    The golden set is the source of truth for what an agent "should" do.
    New cassettes are compared against it to detect regressions.
    """

    def __init__(
        self,
        name: str = "",
        description: str = "",
        version: int = 1,
        thresholds: Thresholds | None = None,
    ):
        self.id: str = str(uuid.uuid4())
        self.name: str = name
        self.description: str = description
        self.version: int = version
        self.created_at: float = time.time()
        self.updated_at: float = time.time()
        self.thresholds: Thresholds = thresholds or Thresholds()
        self._cassettes: list[Cassette] = []
        self.metadata: dict = {}

    @property
    def cassettes(self) -> list[Cassette]:
        return list(self._cassettes)

    @property
    def cassette_count(self) -> int:
        return len(self._cassettes)

    def add_cassette(self, cassette: Cassette) -> None:
        """Add a cassette to the golden set."""
        c = copy.deepcopy(cassette)
        c.compute_metrics()
        c.compute_fingerprint()
        self._cassettes.append(c)
        self.updated_at = time.time()

    def get_primary_cassette(self) -> Cassette | None:
        """Get the first (primary) cassette in the golden set."""
        return self._cassettes[0] if self._cassettes else None

    def compare(
        self,
        candidate: Cassette,
        thresholds: Thresholds | None = None,
    ) -> ComparisonResult:
        """Compare a candidate cassette against this golden set.

        Uses the primary (first) cassette as the baseline.  If custom
        thresholds are provided they override the golden-set defaults.

        Returns a ComparisonResult with per-field pass/fail.
        """
        golden = self.get_primary_cassette()
        if golden is None:
            return ComparisonResult(
                passed=False,
                golden_name=self.name,
                golden_version=self.version,
                fields=[ComparisonField(
                    name="golden_set_empty",
                    passed=False,
                    message="Golden set has no cassettes to compare against.",
                )],
            )

        golden.compute_metrics()
        candidate.compute_metrics()
        t = thresholds or self.thresholds
        fields: list[ComparisonField] = []

        # Tool sequence
        if t.tool_sequence_must_match:
            golden_seq = golden.get_tool_sequence()
            candidate_seq = candidate.get_tool_sequence()
            match = golden_seq == candidate_seq
            fields.append(ComparisonField(
                name="tool_sequence",
                passed=match,
                golden_value=golden_seq,
                candidate_value=candidate_seq,
                message="" if match else (
                    f"Tool sequence changed: {golden_seq} -> {candidate_seq}"
                ),
            ))

        # Output text
        if t.output_must_match:
            match = golden.output_text == candidate.output_text
            fields.append(ComparisonField(
                name="output_text",
                passed=match,
                golden_value=golden.output_text[:200],
                candidate_value=candidate.output_text[:200],
                message="" if match else "Output text differs from golden baseline.",
            ))

        # Token increase ratio
        if t.max_token_increase_ratio is not None and golden.total_tokens > 0:
            ratio = candidate.total_tokens / golden.total_tokens
            passed = ratio <= t.max_token_increase_ratio
            fields.append(ComparisonField(
                name="token_count",
                passed=passed,
                golden_value=golden.total_tokens,
                candidate_value=candidate.total_tokens,
                message="" if passed else (
                    f"Token count increased {ratio:.2f}x "
                    f"(limit: {t.max_token_increase_ratio:.2f}x). "
                    f"{golden.total_tokens} -> {candidate.total_tokens}"
                ),
            ))

        # Cost increase ratio
        if t.max_cost_increase_ratio is not None and golden.total_cost_usd > 0:
            ratio = candidate.total_cost_usd / golden.total_cost_usd
            passed = ratio <= t.max_cost_increase_ratio
            fields.append(ComparisonField(
                name="cost",
                passed=passed,
                golden_value=golden.total_cost_usd,
                candidate_value=candidate.total_cost_usd,
                message="" if passed else (
                    f"Cost increased {ratio:.2f}x "
                    f"(limit: {t.max_cost_increase_ratio:.2f}x). "
                    f"${golden.total_cost_usd:.4f} -> ${candidate.total_cost_usd:.4f}"
                ),
            ))

        # Latency increase ratio
        if t.max_latency_increase_ratio is not None and golden.total_duration_ms > 0:
            ratio = candidate.total_duration_ms / golden.total_duration_ms
            passed = ratio <= t.max_latency_increase_ratio
            fields.append(ComparisonField(
                name="latency",
                passed=passed,
                golden_value=golden.total_duration_ms,
                candidate_value=candidate.total_duration_ms,
                message="" if passed else (
                    f"Latency increased {ratio:.2f}x "
                    f"(limit: {t.max_latency_increase_ratio:.2f}x). "
                    f"{golden.total_duration_ms:.0f}ms -> {candidate.total_duration_ms:.0f}ms"
                ),
            ))

        # Absolute token limit
        if t.max_tokens is not None:
            passed = candidate.total_tokens <= t.max_tokens
            fields.append(ComparisonField(
                name="max_tokens",
                passed=passed,
                golden_value=t.max_tokens,
                candidate_value=candidate.total_tokens,
                message="" if passed else (
                    f"Token count {candidate.total_tokens} exceeds limit {t.max_tokens}"
                ),
            ))

        # Absolute cost limit
        if t.max_cost_usd is not None:
            passed = candidate.total_cost_usd <= t.max_cost_usd
            fields.append(ComparisonField(
                name="max_cost",
                passed=passed,
                golden_value=t.max_cost_usd,
                candidate_value=candidate.total_cost_usd,
                message="" if passed else (
                    f"Cost ${candidate.total_cost_usd:.4f} exceeds limit ${t.max_cost_usd:.4f}"
                ),
            ))

        # Absolute latency limit
        if t.max_latency_ms is not None:
            passed = candidate.total_duration_ms <= t.max_latency_ms
            fields.append(ComparisonField(
                name="max_latency",
                passed=passed,
                golden_value=t.max_latency_ms,
                candidate_value=candidate.total_duration_ms,
                message="" if passed else (
                    f"Latency {candidate.total_duration_ms:.0f}ms exceeds limit {t.max_latency_ms:.0f}ms"
                ),
            ))

        all_passed = all(f.passed for f in fields)
        return ComparisonResult(
            passed=all_passed,
            golden_name=self.name,
            golden_version=self.version,
            fields=fields,
        )

    def bump_version(self) -> int:
        """Increment version and return the new version number."""
        self.version += 1
        self.updated_at = time.time()
        return self.version

    # ──────────────────────────────────────────
    # Persistence
    # ──────────────────────────────────────────

    def to_dict(self) -> dict:
        return {
            "evalcraft_golden_set": True,
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "thresholds": self.thresholds.to_dict(),
            "cassettes": [c.to_dict() for c in self._cassettes],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, data: dict) -> GoldenSet:
        gs = cls(
            name=data.get("name", ""),
            description=data.get("description", ""),
            version=data.get("version", 1),
        )
        gs.id = data.get("id", str(uuid.uuid4()))
        gs.created_at = data.get("created_at", time.time())
        gs.updated_at = data.get("updated_at", time.time())
        gs.metadata = data.get("metadata", {})

        if "thresholds" in data:
            gs.thresholds = Thresholds.from_dict(data["thresholds"])

        for c_data in data.get("cassettes", []):
            gs._cassettes.append(Cassette.from_dict(c_data))

        return gs

    def save(self, path: str | Path) -> Path:
        """Save golden set to a JSON file."""
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2, default=str)
        return path

    @classmethod
    def load(cls, path: str | Path) -> GoldenSet:
        """Load golden set from a JSON file."""
        with open(path) as f:
            data = json.load(f)
        return cls.from_dict(data)

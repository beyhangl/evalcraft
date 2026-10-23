"""Domain-neutral scenario execution and business-state assertions."""

from __future__ import annotations

import json
import re
import time
from collections.abc import Callable
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol

from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import Cassette, Span, SpanKind

OutcomeStatus = Literal["succeeded", "blocked", "unknown", "error"]
_STATUSES = {"succeeded", "blocked", "unknown", "error"}


def _json_copy(value: Any) -> Any:
    """Validate persisted observations and detach mutable environment values."""
    _validate_keys(value)
    return json.loads(json.dumps(value, allow_nan=False))


def _validate_keys(value: Any) -> None:
    if isinstance(value, dict):
        for key, child in value.items():
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            _validate_keys(child)
    elif isinstance(value, (list, tuple)):
        for child in value:
            _validate_keys(child)


def _state_copy(value: Any) -> dict:
    if not isinstance(value, dict):
        raise TypeError("state must be a JSON-compatible dictionary")
    return _json_copy(value)


@dataclass
class ScenarioAction:
    """Environment input containing only the action, arguments, and fault.

    Expectations stay with the runner so the adapter cannot derive its outcome
    from the test's expected status, result, or business state.
    """

    action: str
    args: dict
    fault: str | None = None

    def __post_init__(self) -> None:
        if not self.action or not self.action.strip():
            raise ValueError("action must not be empty")
        self.args = _state_copy(self.args)


@dataclass
class ScenarioStep:
    """An action plus independently supplied result/state expectations.

    Dictionary expectations match recursively as subsets. Lists match exactly;
    numbers compare by value and booleans remain distinct from numbers.
    ``expected_result=None`` omits the result assertion. ``fault`` is interpreted
    only by the supplied environment.
    """

    action: str
    args: dict
    expected_status: OutcomeStatus
    expected_result: dict | None = None
    expected_state: dict | None = None
    fault: str | None = None

    def __post_init__(self) -> None:
        if not self.action or not self.action.strip():
            raise ValueError("action must not be empty")
        if self.expected_status not in _STATUSES:
            raise ValueError(f"unsupported expected status: {self.expected_status!r}")
        self.args = _state_copy(self.args)
        if self.expected_result is not None:
            self.expected_result = _state_copy(self.expected_result)
        if self.expected_state is not None:
            self.expected_state = _state_copy(self.expected_state)


@dataclass
class Scenario:
    """A case with a fresh environment and an explicit final-state assertion."""

    name: str
    initial_state: dict
    steps: list[ScenarioStep]
    expected_state: dict

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValueError("scenario name must not be empty")
        self.initial_state = _state_copy(self.initial_state)
        self.expected_state = _state_copy(self.expected_state)
        if not all(isinstance(step, ScenarioStep) for step in self.steps):
            raise TypeError("steps must contain ScenarioStep objects")


@dataclass
class StepOutcome:
    """An environment's observation, including uncertain execution outcomes.

    Return ``unknown`` after an ambiguous provider timeout instead of claiming
    the operation failed or succeeded. Unexpected exceptions are always runner
    failures, even when a step expects the explicit ``error`` status.
    """

    status: OutcomeStatus
    result: Any = None
    error: str | None = None

    def __post_init__(self) -> None:
        if self.status not in _STATUSES:
            raise ValueError(f"unsupported outcome status: {self.status!r}")


class ScenarioEnvironment(Protocol):
    """Adapter boundary for an isolated stateful application or simulator."""

    def execute(self, action: ScenarioAction) -> StepOutcome: ...

    def snapshot(self) -> dict: ...

    def close(self) -> None: ...


@dataclass
class StepObservation:
    """Detached before/after evidence and assertion failures for one step."""

    index: int
    action: str
    args: dict
    fault: str | None
    before: dict
    after: dict | None
    outcome: StepOutcome
    failures: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {**asdict(self), "passed": self.passed}


@dataclass
class ScenarioReport:
    name: str
    initial_state: dict
    expected_state: dict
    final_state: dict | None
    steps: list[StepObservation]
    failures: list[str]
    cassette: Cassette

    @property
    def passed(self) -> bool:
        return not self.failures

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "passed": self.passed,
            "initial_state": deepcopy(self.initial_state),
            "expected_state": deepcopy(self.expected_state),
            "final_state": deepcopy(self.final_state),
            "steps": [step.to_dict() for step in self.steps],
            "failures": list(self.failures),
            "cassette": self.cassette.to_dict(),
        }


@dataclass
class ScenarioSuiteReport:
    cases: list[ScenarioReport]

    @property
    def passed(self) -> bool:
        return bool(self.cases) and all(case.passed for case in self.cases)

    @property
    def failures(self) -> list[str]:
        return [f"{case.name}: {failure}" for case in self.cases for failure in case.failures]

    def to_dict(self) -> dict:
        return {
            "passed": self.passed,
            "total_cases": len(self.cases),
            "passed_cases": sum(case.passed for case in self.cases),
            "failed_cases": sum(not case.passed for case in self.cases),
            "cases": [case.to_dict() for case in self.cases],
        }


def _mismatches(expected: Any, actual: Any, path: str) -> list[str]:
    if isinstance(expected, dict):
        if not isinstance(actual, dict):
            return [f"{path}: expected a mapping, got {actual!r}"]
        failures = []
        for key, value in expected.items():
            child = f"{path}.{key}"
            if key not in actual:
                failures.append(f"{child}: missing key (expected {value!r})")
            else:
                failures.extend(_mismatches(value, actual[key], child))
        return failures
    if not _equal_value(expected, actual):
        return [f"{path}: expected {expected!r}, got {actual!r}"]
    return []


def _equal_value(expected: Any, actual: Any) -> bool:
    # Python otherwise considers True == 1, including inside lists/dictionaries.
    if isinstance(expected, bool) != isinstance(actual, bool):
        return False
    if isinstance(expected, list):
        return isinstance(actual, list) and len(expected) == len(actual) and all(
            _equal_value(left, right) for left, right in zip(expected, actual, strict=True)
        )
    if isinstance(expected, dict):
        return isinstance(actual, dict) and expected.keys() == actual.keys() and all(
            _equal_value(value, actual[key]) for key, value in expected.items()
        )
    return bool(expected == actual)


def _write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write("\n")


def _save_report(report: ScenarioReport, output_dir: Path) -> None:
    _write_json(output_dir / "cassette.json", report.cassette.to_dict())
    _write_json(output_dir / "report.json", report.to_dict())


def run_scenario(
    scenario: Scenario,
    environment_factory: Callable[[dict], ScenarioEnvironment],
    *,
    output_dir: str | Path | None = None,
) -> ScenarioReport:
    """Execute real environment code against explicit offline expectations.

    A factory receives a deep copy of the initial state. Failed assertions do
    not stop later steps, so recovery can be observed. Unexpected execution or
    snapshot exceptions stop the case and fail it. Cleanup errors also fail the
    case. When saving, ``output_dir`` must be a new directory; this runner never
    replaces an existing report, cassette, or baseline.
    """
    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=False)
    # Keep expectations outside the environment's mutable reach.
    case = deepcopy(scenario)
    capture = CaptureContext(name=case.name, framework="stateful-scenario")
    cassette = capture.cassette
    cassette.metadata = {
        "evalcraft_scenario": {"version": 1},
        "observation_kind": "scenario_action_attempts",
        "initial_state": deepcopy(case.initial_state),
        "expected_state": deepcopy(case.expected_state),
    }
    report = ScenarioReport(
        case.name, deepcopy(case.initial_state), deepcopy(case.expected_state),
        None, [], [], cassette,
    )
    environment: ScenarioEnvironment | None = None
    with capture:
        try:
            environment = environment_factory(deepcopy(case.initial_state))
            for index, step in enumerate(case.steps):
                before = _state_copy(environment.snapshot())
                started = time.perf_counter()
                attempt = Span(
                    kind=SpanKind.AGENT_STEP,
                    name=step.action,
                    input=deepcopy(step.args),
                    metadata={"evalcraft_scenario": {
                        "version": 1, "step": index, "action": step.action,
                        "fault": step.fault, "event": "action_attempt",
                    }},
                )
                cassette.add_span(attempt)
                failures: list[str] = []
                stopped = False
                try:
                    action = ScenarioAction(step.action, deepcopy(step.args), step.fault)
                    outcome = environment.execute(action)
                    if not isinstance(outcome, StepOutcome):
                        raise TypeError("execute() must return StepOutcome")
                    outcome = StepOutcome(**_json_copy(asdict(outcome)))
                except Exception as exc:
                    outcome = StepOutcome("error", error=f"{type(exc).__name__}: {exc}")
                    failures.append(f"step[{index}]: unexpected execution error: {outcome.error}")
                    stopped = True
                after: dict | None = None
                try:
                    after = _state_copy(environment.snapshot())
                except Exception as exc:
                    failures.append(f"step[{index}]: snapshot error: {type(exc).__name__}: {exc}")
                    stopped = True
                failures.extend(_mismatches(
                    step.expected_status, outcome.status, f"step[{index}].status",
                ))
                if step.expected_result is not None:
                    failures.extend(_mismatches(
                        step.expected_result, outcome.result, f"step[{index}].result",
                    ))
                if step.expected_state is not None:
                    failures.extend(_mismatches(step.expected_state, after, f"step[{index}].state"))
                observation = StepObservation(
                    index, step.action, deepcopy(step.args), step.fault,
                    before, after, outcome, failures,
                )
                report.steps.append(observation)
                report.failures.extend(failures)
                cassette.add_span(Span(
                    kind=SpanKind.AGENT_STEP,
                    name=f"{step.action}.outcome",
                    parent_id=attempt.id,
                    output=deepcopy(outcome.result),
                    error=outcome.error,
                    duration_ms=(time.perf_counter() - started) * 1000,
                    metadata={
                        "evalcraft_scenario": {
                            "version": 1, "step": index, "action": step.action,
                            "event": "action_outcome", "status": outcome.status,
                        },
                        "before": before, "after": after, "passed": observation.passed,
                    },
                ))
                if stopped:
                    break
            report.final_state = _state_copy(environment.snapshot())
            report.failures.extend(_mismatches(
                case.expected_state, report.final_state, "final_state",
            ))
        except Exception as exc:
            report.failures.append(f"environment error: {type(exc).__name__}: {exc}")
        finally:
            if environment is not None:
                try:
                    environment.close()
                except Exception as exc:
                    report.failures.append(f"cleanup error: {type(exc).__name__}: {exc}")
    cassette.metadata["passed"] = report.passed
    cassette.metadata["failures"] = list(report.failures)
    cassette.metadata["final_state"] = deepcopy(report.final_state)
    cassette.output_text = "passed" if report.passed else "failed"
    if destination is not None:
        _save_report(report, destination)
    return report


def run_scenarios(
    scenarios: list[Scenario],
    environment_factory: Callable[[dict], ScenarioEnvironment],
    *,
    output_dir: str | Path | None = None,
) -> ScenarioSuiteReport:
    """Run isolated cases, optionally writing new per-case and suite artifacts."""
    if not scenarios:
        raise ValueError("a scenario suite must contain at least one case")
    destination = Path(output_dir) if output_dir is not None else None
    if destination is not None:
        destination.mkdir(parents=True, exist_ok=False)
    reports = []
    for index, scenario in enumerate(scenarios):
        slug = re.sub(r"[^a-zA-Z0-9_-]", "_", scenario.name).strip("_")[:80] or "case"
        case_dir = destination / f"{index + 1:03d}-{slug}" if destination is not None else None
        reports.append(run_scenario(scenario, environment_factory, output_dir=case_dir))
    suite = ScenarioSuiteReport(reports)
    if destination is not None:
        _write_json(destination / "report.json", suite.to_dict())
    return suite

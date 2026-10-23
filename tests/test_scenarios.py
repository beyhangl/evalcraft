"""Exercise real state transitions, independent oracles, and recording safety."""

import json
from copy import deepcopy

import pytest

from evalcraft import (
    Cassette,
    Scenario,
    ScenarioAction,
    ScenarioStep,
    StepOutcome,
    assert_tool_called,
    replay,
    run_scenario,
    run_scenarios,
)
from evalcraft.capture.recorder import get_active_context
from evalcraft.core.models import SpanKind


class Inventory:
    """A tiny stateful tool boundary independent of runner implementation."""

    def __init__(self, state):
        self.state = state
        self.closed = False

    def execute(self, step):
        if step.action == "crash":
            self.state["stock"] -= 1
            raise RuntimeError("provider disconnected")
        if step.fault == "timeout":
            self.state["stock"] -= step.args["quantity"]
            return StepOutcome("unknown", {"reason": "provider timeout"})
        if step.action == "inspect":
            return StepOutcome("succeeded", {"stock": self.state["stock"]})
        quantity = step.args["quantity"]
        if quantity > self.state["stock"]:
            return StepOutcome("blocked", {"reason": "insufficient stock"})
        self.state["stock"] -= quantity
        return StepOutcome("succeeded", {"reserved": quantity, "stock": self.state["stock"]})

    def snapshot(self):
        # Intentionally return the mutable source; runner must retain observations.
        return self.state

    def close(self):
        self.closed = True


def inventory_case():
    return Scenario(
        name="reserve inventory",
        initial_state={"stock": 4, "owner": {"tenant": "shop-a"}},
        steps=[
            ScenarioStep("reserve", {"quantity": 3}, "succeeded",
                         expected_result={"reserved": 3}, expected_state={"stock": 1}),
            ScenarioStep("reserve", {"quantity": 2}, "blocked",
                         expected_result={"reason": "insufficient stock"},
                         expected_state={"stock": 1}),
        ],
        expected_state={"stock": 1, "owner": {"tenant": "shop-a"}},
    )


def test_actual_code_runs_and_subset_expectations_pass():
    environments = []

    def factory(state):
        environments.append(Inventory(state))
        return environments[-1]

    report = run_scenario(inventory_case(), factory)
    assert report.passed, report.failures
    assert environments[0].closed
    assert report.final_state["stock"] == 1
    assert report.steps[0].before["stock"] == 4
    assert report.steps[0].after["stock"] == 1
    assert report.steps[1].outcome.status == "blocked"


def test_wrong_business_state_fails_even_with_correct_status():
    case = inventory_case()
    case.steps[0].expected_state = {"stock": 2}
    case.expected_state = {"stock": 99}
    report = run_scenario(case, Inventory)
    assert not report.passed
    assert any("step[0].state.stock: expected 2, got 1" in failure for failure in report.failures)
    assert any("final_state.stock: expected 99, got 1" in failure for failure in report.failures)
    # Failed assertions do not hide later recovery/inspection steps.
    assert len(report.steps) == 2


def test_wrong_status_result_and_missing_state_are_reported():
    case = inventory_case()
    case.steps[0].expected_status = "blocked"
    case.steps[0].expected_result = {"reserved": 9, "receipt": "missing"}
    case.expected_state = {"owner": {"user": "missing"}}
    report = run_scenario(case, Inventory)
    assert not report.passed
    assert any("step[0].status" in failure for failure in report.failures)
    assert any("step[0].result.reserved" in failure for failure in report.failures)
    assert any("step[0].result.receipt: missing key" in failure for failure in report.failures)
    assert any("final_state.owner.user: missing key" in failure for failure in report.failures)


def test_unknown_outcome_does_not_infer_failure_or_roll_back_state():
    case = Scenario(
        "uncertain provider", {"stock": 4},
        [ScenarioStep("reserve", {"quantity": 2}, "unknown", fault="timeout",
                      expected_result={"reason": "provider timeout"},
                      expected_state={"stock": 2})],
        {"stock": 2},
    )
    report = run_scenario(case, Inventory)
    assert report.passed, report.failures
    assert report.steps[0].outcome.status == "unknown"
    assert report.final_state == {"stock": 2}


def test_exception_never_passes_as_an_expected_error():
    case = Scenario(
        "unexpected exception", {"stock": 4},
        [ScenarioStep("crash", {}, "error"), ScenarioStep("inspect", {}, "succeeded")],
        {"stock": 3},
    )
    report = run_scenario(case, Inventory)
    assert not report.passed
    assert len(report.steps) == 1
    assert "unexpected execution error: RuntimeError: provider disconnected" in report.failures[0]
    assert report.steps[0].after == {"stock": 3}


def test_explicit_expected_error_outcome_can_pass():
    class RejectingInventory(Inventory):
        def execute(self, step):
            return StepOutcome("error", {"reason": "invalid item"}, error="invalid item")

    case = Scenario("expected error", {"stock": 4}, [
        ScenarioStep("reserve", {}, "error", expected_result={"reason": "invalid item"}),
    ], {"stock": 4})
    assert run_scenario(case, RejectingInventory).passed


def test_factory_receives_isolated_initial_state_and_repeated_runs_are_independent():
    case = inventory_case()
    original = deepcopy(case)
    suite = run_scenarios([case, case], Inventory)
    assert suite.passed, suite.failures
    assert case == original
    assert [report.steps[0].before["stock"] for report in suite.cases] == [4, 4]


def test_environment_cannot_mutate_expected_oracle_or_action_record():
    class MutatingInventory(Inventory):
        def execute(self, step):
            step.args["quantity"] = 99
            self.state["stock"] = 99
            return StepOutcome("succeeded", {"reserved": 99})

    case = Scenario("independent oracle", {"stock": 4}, [
        ScenarioStep("reserve", {"quantity": 1}, "succeeded",
                     expected_result={"reserved": 1}, expected_state={"stock": 3}),
    ], {"stock": 3})
    original = deepcopy(case)
    report = run_scenario(case, MutatingInventory)
    assert not report.passed
    assert report.steps[0].args == {"quantity": 1}
    assert case == original


def test_environment_receives_only_action_inputs_without_expectations():
    received = []

    class IndependentInventory(Inventory):
        def execute(self, action):
            received.append(action)
            assert isinstance(action, ScenarioAction)
            assert not hasattr(action, "expected_status")
            assert not hasattr(action, "expected_result")
            assert not hasattr(action, "expected_state")
            return super().execute(action)

    report = run_scenario(inventory_case(), IndependentInventory)
    assert report.passed, report.failures
    assert len(received) == 2
    assert received[0].action == "reserve"
    assert received[0].args == {"quantity": 3}


@pytest.mark.parametrize("phase", ["setup", "snapshot", "close"])
def test_environment_lifecycle_errors_fail_case(phase):
    class BrokenInventory(Inventory):
        def __init__(self, state):
            if phase == "setup":
                raise RuntimeError("setup failed")
            super().__init__(state)

        def snapshot(self):
            if phase == "snapshot":
                raise RuntimeError("snapshot failed")
            return super().snapshot()

        def close(self):
            super().close()
            if phase == "close":
                raise RuntimeError("close failed")

    report = run_scenario(inventory_case(), BrokenInventory)
    assert not report.passed
    assert any(f"{phase} failed" in failure for failure in report.failures)
    assert report.cassette.metadata["passed"] is False


def test_post_execution_snapshot_failure_is_failure_and_cleanup_runs():
    environments = []

    class BrokenSnapshot(Inventory):
        def snapshot(self):
            if self.state["stock"] != 4:
                raise RuntimeError("snapshot unavailable")
            return super().snapshot()

    def factory(state):
        environments.append(BrokenSnapshot(state))
        return environments[-1]

    report = run_scenario(inventory_case(), factory)
    assert not report.passed
    assert report.steps[0].after is None
    assert environments[0].closed
    assert any("snapshot unavailable" in failure for failure in report.failures)


@pytest.mark.parametrize("value", [True, [True], [{"count": True}]])
def test_boolean_does_not_match_integer_even_inside_lists(value):
    actual = {"stock": value}
    expected = {"stock": 1 if value is True else [1] if value == [True] else [{"count": 1}]}
    case = Scenario("strict scalar types", actual, [], expected)
    assert not run_scenario(case, Inventory).passed


def test_lists_match_exactly_including_dictionary_contents():
    state = {"receipts": [{"id": "one", "extra": True}]}
    case = Scenario("exact receipt list", state, [], {"receipts": [{"id": "one"}]})
    assert not run_scenario(case, Inventory).passed


def test_snapshots_and_outcomes_must_be_json_serializable():
    class NonSerializableResult(Inventory):
        def execute(self, step):
            return StepOutcome("succeeded", object())

    report = run_scenario(inventory_case(), NonSerializableResult)
    assert not report.passed
    # Invalid evidence is an explicit error, never silently stringified.
    assert any("not JSON serializable" in failure for failure in report.failures)
    json.dumps(report.to_dict(), allow_nan=False)


def test_invalid_outcome_shape_is_an_explicit_failure():
    class IncorrectAdapter(Inventory):
        def execute(self, step):
            return {"status": "succeeded"}

    report = run_scenario(inventory_case(), IncorrectAdapter)
    assert not report.passed
    assert any("execute() must return StepOutcome" in failure for failure in report.failures)


@pytest.mark.parametrize("invalid", ["success", "denied", ""])
def test_invalid_statuses_rejected_before_execution(invalid):
    with pytest.raises(ValueError, match="unsupported expected status"):
        ScenarioStep("reserve", {}, invalid)
    with pytest.raises(ValueError, match="unsupported outcome status"):
        StepOutcome(invalid)


def test_artifacts_can_be_replayed_but_do_not_fabricate_tool_execution(tmp_path):
    path = tmp_path / "new-run"
    report = run_scenario(inventory_case(), Inventory, output_dir=path)
    assert report.passed, report.failures
    recorded = Cassette.load(path / "cassette.json")
    assert recorded.metadata["evalcraft_scenario"] == {"version": 1}
    assert recorded.metadata["passed"] is True
    assert len(recorded.spans) == 4
    assert all(span.kind == SpanKind.AGENT_STEP for span in recorded.spans)
    assert recorded.spans[-1].metadata["evalcraft_scenario"]["status"] == "blocked"
    assert not assert_tool_called(replay(path / "cassette.json"), "reserve").passed
    saved_report = json.loads((path / "report.json").read_text())
    assert saved_report["passed"] is True
    assert saved_report["steps"][0]["after"]["stock"] == 1
    assert saved_report["expected_state"] == inventory_case().expected_state


def test_real_environment_tool_recording_uses_the_active_capture(tmp_path):
    class RecordingInventory(Inventory):
        def __init__(self, state):
            super().__init__(state)
            self.recorder = get_active_context()
            assert self.recorder is not None

        def execute(self, step):
            outcome = super().execute(step)
            if outcome.status == "succeeded":
                self.recorder.record_tool_call(step.action, args=step.args, result=outcome.result)
            return outcome

    report = run_scenario(inventory_case(), RecordingInventory, output_dir=tmp_path / "run")
    assert report.passed, report.failures
    assert len(report.cassette.get_tool_calls()) == 1
    assert assert_tool_called(replay(tmp_path / "run" / "cassette.json"), "reserve", times=1).passed
    assert get_active_context() is None


def test_output_directory_must_be_new_before_environment_is_created(tmp_path):
    existing = tmp_path / "recordings"
    existing.mkdir()
    baseline = existing / "cassette.json"
    baseline.write_text("human-reviewed baseline")
    called = []

    def factory(state):
        called.append(True)
        return Inventory(state)

    with pytest.raises(FileExistsError):
        run_scenario(inventory_case(), factory, output_dir=existing)
    assert not called
    assert baseline.read_text() == "human-reviewed baseline"


def test_suite_isolates_failures_and_sanitizes_artifact_names(tmp_path):
    passing = inventory_case()
    passing.name = "../../outside"
    failing = inventory_case()
    failing.name = passing.name
    failing.expected_state = {"stock": 123}
    directory = tmp_path / "suite"
    suite = run_scenarios([failing, passing], Inventory, output_dir=directory)
    assert not suite.passed
    assert len(suite.cases) == 2
    assert suite.cases[1].passed
    summary = json.loads((directory / "report.json").read_text())
    assert summary["passed_cases"] == 1
    assert summary["failed_cases"] == 1
    assert len(list(directory.glob("*/cassette.json"))) == 2
    assert all(path.parent == directory for path in directory.iterdir())


def test_outer_capture_context_is_restored():
    from evalcraft import CaptureContext

    with CaptureContext("outer") as outer:
        report = run_scenario(inventory_case(), Inventory)
        assert report.passed
        assert get_active_context() is outer
        assert not outer.cassette.spans


def test_empty_suite_rejected_instead_of_reporting_zero_coverage_as_passed():
    with pytest.raises(ValueError, match="at least one case"):
        run_scenarios([], Inventory)


def test_json_object_keys_must_not_collide_after_serialization():
    with pytest.raises(TypeError, match="keys must be strings"):
        Scenario("ambiguous keys", {"values": {"1": "a", 1: "b"}}, [], {})

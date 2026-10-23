"""Run real state transitions against explicit expectations, without model keys.

    python examples/stateful_scenarios.py
    python examples/stateful_scenarios.py --output-dir /tmp/new-inventory-scenarios

The optional output directory must not already exist. Each new run preserves its
cassette and report without replacing a prior recording.
"""

from __future__ import annotations

import argparse

from evalcraft import Scenario, ScenarioAction, ScenarioStep, StepOutcome, run_scenarios
from evalcraft.capture.recorder import get_active_context


class InventoryEnvironment:
    """A mutable local tool; production stores and network calls are not used."""

    def __init__(self, initial_state: dict) -> None:
        self.state = initial_state
        self.recorder = get_active_context()

    def execute(self, action: ScenarioAction) -> StepOutcome:
        if action.action != "reserve":
            raise ValueError(f"Unsupported action: {action.action}")
        quantity = action.args["quantity"]
        if type(quantity) is not int or quantity <= 0:
            return StepOutcome("blocked", {"reason": "invalid_quantity"})
        if quantity > self.state["available"]:
            return StepOutcome("blocked", {"reason": "insufficient_stock"})
        self.state["available"] -= quantity
        self.state["reserved"] += quantity
        result = {"reserved": quantity}
        if self.recorder is not None:
            # This records the observed local operation, only after it executed.
            self.recorder.record_tool_call("reserve", args=action.args, result=result)
        return StepOutcome("succeeded", result)

    def snapshot(self) -> dict:
        return dict(self.state)

    def close(self) -> None:
        pass  # No external resources in this environment.


def inventory_case() -> Scenario:
    """Expected values are authored independently of the environment's output."""
    return Scenario(
        name="reserve-with-insufficient-stock",
        initial_state={"available": 4, "reserved": 0},
        steps=[
            ScenarioStep(
                "reserve", {"quantity": 3}, "succeeded",
                expected_result={"reserved": 3},
                expected_state={"available": 1, "reserved": 3},
            ),
            ScenarioStep(
                "reserve", {"quantity": 2}, "blocked",
                expected_result={"reason": "insufficient_stock"},
                expected_state={"available": 1, "reserved": 3},
            ),
        ],
        expected_state={"available": 1, "reserved": 3},
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", help="New directory for reports and cassettes")
    args = parser.parse_args()
    suite = run_scenarios([inventory_case()], InventoryEnvironment, output_dir=args.output_dir)
    for case in suite.cases:
        print(f"{case.name}: {'PASS' if case.passed else 'FAIL'}")
        for step in case.steps:
            print(f"  {step.action}: {step.outcome.status}; state={step.after}")
        for failure in case.failures:
            print(f"  {failure}")
    if args.output_dir:
        print(f"Artifacts: {args.output_dir}")
    if not suite.passed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

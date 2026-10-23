"""Offline stateful scenario tests with explicit expectations and cassettes.

The runner executes a supplied environment; it does not call a model, invent
expected values, or replay recorded state in place of application code. Use
isolated fake tools in environments to keep a suite offline and free of side
effects. Scenario attempts are recorded as agent steps, not proof that an
underlying business operation executed.
"""

from evalcraft.scenarios.runner import (
    Scenario,
    ScenarioAction,
    ScenarioEnvironment,
    ScenarioReport,
    ScenarioStep,
    ScenarioSuiteReport,
    StepObservation,
    StepOutcome,
    run_scenario,
    run_scenarios,
)

__all__ = [
    "Scenario",
    "ScenarioAction",
    "ScenarioEnvironment",
    "ScenarioReport",
    "ScenarioStep",
    "ScenarioSuiteReport",
    "StepObservation",
    "StepOutcome",
    "run_scenario",
    "run_scenarios",
]

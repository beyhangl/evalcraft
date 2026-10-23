# Stateful scenarios

Test application decisions and resulting business state across multiple actions.
Each scenario starts from fresh state, executes real environment code, and checks
independently authored expectations after selected steps and at the end. Keep
cassettes: the runner records what it observed while the code executes.

This API is part of the **unreleased source checkout**. Install this checkout
until a release containing `evalcraft.scenarios` is available:

```bash
python -m pip install -e /path/to/evalcraft
python examples/stateful_scenarios.py
```

The example needs only Evalcraft. It reserves three of four inventory units,
then blocks a request for two more while asserting that inventory did not change:

```text
reserve-with-insufficient-stock: PASS
  reserve: succeeded; state={'available': 1, 'reserved': 3}
  reserve: blocked; state={'available': 1, 'reserved': 3}
```

See the complete [runnable example](https://github.com/beyhangl/evalcraft/blob/main/examples/stateful_scenarios.py).
There are no model calls, API keys, or external stores in that example.

## Choose the right test

| Test | Execution | A pass establishes |
|---|---|---|
| Recorded-run checks, `replay()` | Reads a saved cassette | The recorded observations satisfy the assertions |
| [Playback](playback.md) | Runs current agent code with recorded model replies | The code handles that recorded interaction and makes matching requests |
| Stateful scenarios | Runs current environment code with supplied actions and initial state | The tested actions satisfy explicit decision, result, and business-state expectations |
| [Live evaluation](live-eval.md) | Runs current code with a live model | The sampled model/prompt/code combination satisfies the configured checks; paid APIs cost money |

A synthetic scenario does not measure what a live model will decide. The runner
does not automatically sandbox an environment or block its network access. Use
isolated local tools, as in the examples, to keep scenario runs offline. Any
network or paid calls introduced by your own adapter remain your responsibility.

## Define a case and an environment

Use `ScenarioStep` to author expectations. The environment receives a separate
`ScenarioAction` containing only `action`, `args`, and optional `fault`. Expected
status, result, and state stay with the runner.

```python
from evalcraft import Scenario, ScenarioStep, StepOutcome, run_scenario

class Inventory:
    def __init__(self, initial_state):
        self.state = initial_state

    def execute(self, action):
        if action.action != "reserve":
            raise ValueError(f"Unsupported action: {action.action}")
        quantity = action.args["quantity"]
        if type(quantity) is not int or quantity <= 0:
            return StepOutcome("blocked", {"reason": "invalid_quantity"})
        if quantity > self.state["available"]:
            return StepOutcome("blocked", {"reason": "insufficient_stock"})
        self.state["available"] -= quantity
        return StepOutcome("succeeded", {"reserved": quantity})

    def snapshot(self):
        return dict(self.state)

    def close(self):
        pass

case = Scenario(
    name="insufficient-stock",
    initial_state={"available": 1},
    steps=[ScenarioStep(
        "reserve", {"quantity": 2}, "blocked",
        expected_result={"reason": "insufficient_stock"},
        expected_state={"available": 1},
    )],
    expected_state={"available": 1},
)
report = run_scenario(case, Inventory)
assert report.passed, report.failures
```

The factory gets a deep copy of the initial state on each run. The runner also
detaches action arguments and snapshots, so a later mutation cannot rewrite an
earlier observation or the expected values. Construct expected values from the
business rule; do not derive them by running the implementation under test.

State and result expectations are recursive dictionary subsets. Extra mapping
keys are permitted. Lists match exactly, including mappings inside lists.
Numbers compare by value, while booleans remain distinct from numbers. Use
`expected_result=None` to omit a result check. All snapshots and persisted
observations must be JSON-compatible; object keys must be strings.

`expected_state` on a step checks the snapshot immediately after that step.
`Scenario.expected_state` is required and checks the final snapshot. Expectations
are not a substitute for inspecting authoritative state: adapters must read their
actual local store or provider simulator in `snapshot()`.

## Outcomes, faults, and failures

An environment returns one of four statuses:

- `succeeded`: the environment observed the action succeeding.
- `blocked`: the environment rejected the action.
- `unknown`: the action's outcome is uncertain, such as a timeout after a
  provider may have accepted it. Assert the observed state and reconcile later.
- `error`: an anticipated error outcome explicitly returned by the adapter.

`fault` is an optional host-controlled input interpreted by the environment.
It is not automatically injected into a provider, and it must not be exposed as
an agent-controlled bypass. For example, a refund simulator can interpret
`fault="timeout_after_commit"`, return `unknown`, then verify the receipt in a
later `reconcile` action.

An unexpected exception from setup, execution, a snapshot, or cleanup fails the
case. Throwing an exception never passes merely because a step expects `error`.
Assertion mismatches are collected and later steps still execute, allowing
recovery to be inspected. Unexpected execution or snapshot errors stop the case.
An empty suite is rejected rather than returning a green result with no coverage.

## Save reports and keep cassettes

```python
from evalcraft import run_scenarios

suite = run_scenarios(
    [case], Inventory,
    output_dir="/tmp/inventory-scenarios-new-run",
)
assert suite.passed, suite.failures
```

The output directory **must not already exist**, including when it is empty.
The runner refuses it before creating an environment. Choose a new path for each
run; do not overwrite or re-record a baseline to fix a failing test.

The root `report.json` summarizes the suite. Each indexed case directory contains
`report.json` and `cassette.json`. Reports include before/after snapshots,
observed outcomes, explicit final expectations, and failures. Scenario names are
sanitized for artifact paths, and repeated names remain separate cases.

The cassette records informational `AGENT_STEP` attempts and outcomes with
versioned `evalcraft_scenario` metadata. **An attempted action is not evidence
that a tool or external effect executed.** The runner does not fabricate
`TOOL_CALL` or `TOOL_RESULT` spans. These cassettes can be inspected using existing
recorded-run tooling, but they do not contain model responses for playback unless
your environment also captures those responses.

The factory, execution, snapshots, and cleanup run inside a `CaptureContext`.
An environment can use `get_active_context()` to record its actual observed
tool calls, as the complete inventory example does. Record execution only where
the underlying boundary actually ran; keep blocked attempts informational.

Saved arguments, results, state, and error strings can contain sensitive data.
Review or redact your adapter's output before sharing scenario artifacts.

## Start with refunds

Pactrun supplies an optional reusable refund environment and independently
authored case pack. Install **both matching source checkouts** until releases
containing the new API and case pack are available:

```bash
python -m pip install -e /path/to/evalcraft -e /path/to/agentpact
```

```python
from evalcraft import run_scenarios
from pactrun.scenarios import refund_environment, refund_scenarios

suite = run_scenarios(refund_scenarios(), refund_environment)
assert suite.passed, suite.failures
```

The synthetic environment uses isolated durable local state. It covers amount
boundaries, ownership, approvals, uncertain results, concurrency, restart, and
receipt reconciliation. Approval issuance, identity, and fault injection belong
to the test host. No real payments or authenticated customer approval service
are provided by this simulator.

See the [refund scenario guide](https://github.com/beyhangl/pactrun/blob/main/docs/STATEFUL_SCENARIOS.md),
[underlying workflow guide](https://github.com/beyhangl/pactrun/blob/main/docs/SUPPORT_REFUND.md),
[case pack](https://github.com/beyhangl/pactrun/blob/main/pactrun/scenarios/refund_cases.py),
and [environment](https://github.com/beyhangl/pactrun/blob/main/pactrun/scenarios/refund_environment.py).
Add customer-owned rules as new explicit cases. For another domain, implement
`execute(ScenarioAction)`, `snapshot()`, and `close()`, then reuse the same runner.

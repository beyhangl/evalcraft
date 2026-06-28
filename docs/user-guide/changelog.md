# Changelog

All notable changes to Evalcraft are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.5.0] — 2026-06-16

### Added
- **Deterministic loop / repetition detection** ($0, offline, no model call): `assert_no_loops` / `detect_loops` flag an agent stuck repeating the same tool call (same `tool_args`) or the same/near-duplicate step output; `assert_no_repeated_tool_calls` is the focused tool-only check. See [Loop Detection](loop-detection.md).
- `generate-tests` auto-emits an `assert_no_loops` guard when the recorded baseline has tool calls and no loops of its own.

---

## [0.4.0] — 2026-06-16

### Added
- **Deterministic structured-output & tool-call-argument scorers** ($0, offline, no model call): `assert_output_json`, `assert_output_json_schema` (dict / `.json` path / inline JSON / pydantic model; pure-stdlib subset validator that upgrades to full Draft 2020-12 when `jsonschema` is installed), `assert_output_has_keys`, `assert_output_field`, `assert_output_value_in`, `assert_output_value_in_range`, `assert_match_groups` (regex capture groups), and `assert_tool_args_match_schema` (validate recorded tool-call arguments against a schema). See [Structured Output](structured-output.md).
- `generate-tests` auto-emits `assert_output_json` + `assert_output_has_keys` tests when a recorded output is JSON.

---

## [0.3.1] — 2026-06-16

### Fixed
- README logo now renders on the PyPI project page (switched from a repo-relative image path to an absolute URL). No SDK or docs behavior changes.

---

## [0.3.0] — 2026-06-01

### Added
- `evalcraft check-stale` — detect cassettes recorded against a retired/swapped model (CRITICAL, non-zero exit for CI) or a drifted prompt (WARNING), by activating the provenance each cassette records. See [Check Stale](check-stale.md).

---

## [0.1.0] — 2026-03-05

Initial public release of Evalcraft — the pytest for AI agents.

### Added

#### Core data model
- **`Span`** — atomic unit of capture, recording every LLM call, tool invocation, agent step, user input, and output with timing, token usage, and cost metadata
- **`Cassette`** — the fundamental recording unit that stores all spans from a single agent execution; supports fingerprinting for change detection, aggregate metrics, and JSON serialization/deserialization
- **`AgentRun`** — wrapper for live or replayed agent results
- **`EvalResult` / `AssertionResult`** — structured pass/fail results for assertions with score tracking
- **`SpanKind`** enum: `llm_request`, `llm_response`, `tool_call`, `tool_result`, `agent_step`, `user_input`, `agent_output`
- **`TokenUsage`** dataclass tracking prompt, completion, and total tokens

#### Capture
- **`capture()`** context manager — instrument any code block to record spans into a cassette
- **`CaptureContext`** — configurable capture session with name, agent name, framework tag, and optional auto-save path

#### Replay
- **`ReplayEngine`** — feeds recorded LLM responses back without making real API calls
- Tool result overriding for isolated replay testing
- **`ReplayDiff`** — compare two cassettes and detect changes in tool sequence, output text, token count, cost, and span count

#### Mock
- **`MockLLM`** — deterministic LLM fake with pattern-based response matching (`"*"` wildcard), token usage simulation, cost tracking, and automatic span recording
- **`MockTool`** — configurable tool fake with `.returns()` / `.raises()` / `.side_effect()` control

#### Eval scorers — 8 built-in assertions
| Assertion | Description |
|---|---|
| `assert_tool_called` | Verify a tool was invoked; supports `times`, `with_args`, `before`, `after` |
| `assert_tool_order` | Verify tool call sequence (strict or subsequence mode) |
| `assert_no_tool_called` | Verify a tool was never invoked |
| `assert_output_contains` | Verify agent output contains a substring |
| `assert_output_matches` | Verify agent output matches a regex pattern |
| `assert_cost_under` | Enforce a cost budget in USD |
| `assert_latency_under` | Enforce a latency budget in milliseconds |
| `assert_token_count_under` | Enforce a token budget |

**`Evaluator`** — compose multiple assertions into a single evaluation with aggregate scoring.

#### Framework adapters — 4 adapters
| Adapter | Frameworks |
|---|---|
| `OpenAIAdapter` | OpenAI Python SDK (`chat.completions.create`, sync + async) |
| `AnthropicAdapter` | Anthropic Python SDK (`messages.create`, sync + async); built-in Claude pricing table |
| `LangGraphAdapter` | LangGraph compiled graphs — node executions, LLM calls, tool calls |
| `CrewAIAdapter` | CrewAI `Crew` — kickoff timing, per-agent tool calls, task completions, delegations |

#### pytest plugin (`pytest-evalcraft`)
Auto-registered via `entry_points` — zero-config activation when evalcraft is installed.

**Fixtures:** `capture_context`, `mock_llm`, `mock_tool`, `cassette`, `replay_engine`, `evalcraft_cassette_dir`

**Markers:**
- `@pytest.mark.evalcraft_cassette(path)` — load a cassette for replay-based assertions
- `@pytest.mark.evalcraft_capture(name, save)` — auto-capture the test's agent run
- `@pytest.mark.evalcraft_agent` — tag tests as agent evaluation tests for filtering

**CLI options:** `--cassette-dir DIR`, `--evalcraft-record {none,new,all}`

**Terminal summary:** per-test agent run metrics table (tokens, cost, tools, latency, fingerprint) appended to pytest output.

#### CLI (`evalcraft`)
| Command | Description |
|---|---|
| `evalcraft capture <script>` | Run a Python script under capture and save the cassette |
| `evalcraft replay <cassette>` | Replay a cassette and display metrics (`--verbose` shows all spans) |
| `evalcraft diff <old> <new>` | Compare two cassettes side-by-side (`--json` for CI) |
| `evalcraft eval <cassette>` | Run assertions with cost/token/latency/tool thresholds; exits 1 on failure |
| `evalcraft info <cassette>` | Inspect cassette metadata, metrics, tool sequence, and spans |
| `evalcraft mock <cassette>` | Generate ready-to-use `MockLLM` and `MockTool` Python fixtures |

#### Project infrastructure
- MIT license, Python 3.9–3.13 support
- Optional dependency groups: `[pytest]`, `[openai]`, `[anthropic]`, `[langchain]`, `[crewai]`, `[all]`
- Hatchling build system, Ruff linting, mypy strict type checking
- GitHub Actions CI and PyPI publish workflows
- 260 tests at release

[0.1.0]: https://github.com/beyhangl/evalcraft/releases/tag/v0.1.0

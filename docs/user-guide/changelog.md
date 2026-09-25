# Changelog

All notable changes to Evalcraft are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [0.9.0] — 2026-09-25

### Added
- **Tool-definition drift.** Adapters record tool names, descriptions and schema hashes. `check-stale --tools tools.json` warns (`tool_drift`) on added, removed or changed tools, and names the case where parameters changed but the description did not.
- **Run-time values in a recording.** `check-stale` warns (`volatile_content`) when a UUID, timestamp or temp path was recorded in what the agent sent.
- **Model aliases.** Adapters record the requested model id when a different snapshot answered. INFO `floating_model_alias` per recording, WARNING `model_alias_moved` when one id was served by different snapshots across cassettes. See [Check Stale](check-stale.md).

### Changed
- For 0.9+ cassettes, `model_retired` judges the model id the code asked for, so a snapshot served for an alias still listed in `--models` is no longer a CRITICAL false alarm.
- `check-stale --json` adds a top-level `across_cassettes` list.

---

## [0.8.0] — 2026-09-24

### Changed (behaviour)
- **A plain `pytest` never writes a cassette.** Capture writes now follow `--evalcraft-record`: `none` (default) never writes, `new` writes only missing cassettes, `all` overwrites.
- **A missing cassette fails in CI** instead of skipping, so deleting a recording can't leave CI green. `--evalcraft-missing=fail|skip` overrides. See [pytest plugin](pytest-plugin.md).

### Fixed
- The quickstart's `pytest --evalcraft` flag did not exist; the scaffold failed on its first run (`add_span` did not update metrics); its replay tests could never pass (mismatched cassette names); `init` aborted without a terminal. All fixed. `init` now ships a sample recording, so a fresh scaffold is fully green.
- `check-stale` now treats Claude Opus 5.5 (always-on thinking) recordings without thinking blocks as CRITICAL.

### Added
- An Agent Skill inside the package (`uvx library-skills --claude --skill evalcraft`), `py.typed`, the `examples/silent_tool_failure.py` demo, `AGENTS.md` and `SECURITY.md`.

---

## [0.7.0] — 2026-09-21

Correctness and repositioning release. Existing cassettes are unaffected.

### Fixed
- **Cache-aware cost.** `TokenUsage` now segments prompt-cache tiers (`cache_read_tokens` / `cache_write_tokens`) and prices each separately. Billing cached input at the full rate overstated cache-heavy agent loops by up to an order of magnitude (~6x on a realistic 100k-context loop). `prompt_tokens` now consistently means **fresh, uncached** input across providers.
- **Opaque reasoning state.** Anthropic extended-thinking blocks (signed `thinking` / `redacted_thinking`) are captured instead of dropped, and `check-stale` reports a CRITICAL `reasoning_state_missing` when a reasoning-model cassette lacks them — replaying those is invalid, not just lossy.

### Changed
- Dropped EOL Python 3.9 (minimum **3.10**); `pytest` extra now requires **pytest ≥ 8**.
- **Repositioned** — the docs lead with the failure this catches (an agent that returns `200 OK`, reports "task completed", and skips the tool call) plus cost budgets, rather than the record/replay mechanism.
- **Honest caveats expanded** — recorded-run tooling is not unique (Docker `cagent`, EvalView `model-check`); a committed baseline is only trustworthy if nothing rewrites it.

### Documentation
- [What replay does and doesn't test](replay.md#what-replay-does-and-doesnt-test) — `replay()` does not run your agent, so a green replay is not proof your current code works.

---

## [0.6.0] — 2026-06-16

### Added
- **`assert_tool_trajectory(cassette, expected_tools, mode=...)`** — deterministic, `$0` tool-trajectory matching in four modes: `strict` (exact order), `unordered` (same multiset, any order), `subset` (no unexpected tools), `superset` (all required tools present). Complements `assert_tool_order`.

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

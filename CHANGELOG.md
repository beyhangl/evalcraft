# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] — 2026-03-05

Initial public release of Evalcraft — the pytest for AI agents.

### Added

#### Core data model
- `Span` — atomic unit of capture, recording every LLM call, tool invocation, agent step, user input, and output with timing, token usage, and cost metadata
- `Cassette` — the fundamental recording unit that stores all spans from a single agent execution; supports fingerprinting for change detection, aggregate metrics, and JSON serialization/deserialization
- `AgentRun` — wrapper for live or replayed agent results
- `EvalResult` / `AssertionResult` — structured pass/fail results for assertions with score tracking
- `SpanKind` enum: `llm_request`, `llm_response`, `tool_call`, `tool_result`, `agent_step`, `user_input`, `agent_output`
- `TokenUsage` dataclass tracking prompt, completion, and total tokens

#### Capture
- `capture()` context manager — instrument any code block to record spans into a cassette
- `CaptureContext` — configurable capture session with name, agent name, framework tag, and optional auto-save path

#### Replay
- `ReplayEngine` — feeds recorded LLM responses back without making real API calls
- Tool result overriding for isolated replay testing
- `ReplayDiff` — compare two cassettes and detect changes in tool sequence, output text, token count, cost, and span count

#### Mock
- `MockLLM` — deterministic LLM fake with pattern-based response matching (`"*"` wildcard), token usage simulation, cost tracking, and automatic span recording
- `MockTool` — configurable tool fake with `.returns()` / `.raises()` / `.side_effect()` control

#### Eval scorers (8 built-in assertions)
- `assert_tool_called(cassette, tool_name, times=None, with_args=None, before=None, after=None)` — verify a tool was invoked, with optional count, arg, and ordering constraints
- `assert_tool_order(cassette, expected_order, strict=False)` — verify tool call sequence (strict or subsequence mode)
- `assert_no_tool_called(cassette, tool_name)` — verify a tool was never invoked
- `assert_output_contains(cassette, substring, case_sensitive=True)` — verify agent output text
- `assert_output_matches(cassette, pattern)` — verify agent output against a regex pattern
- `assert_cost_under(cassette, max_usd)` — budget enforcement
- `assert_latency_under(cassette, max_ms)` — latency enforcement
- `assert_token_count_under(cassette, max_tokens)` — token budget enforcement
- `Evaluator` — compose multiple assertions into a single evaluation with aggregate scoring

#### Framework adapters (4 adapters)
- `OpenAIAdapter` — patches the OpenAI Python SDK (`chat.completions.create`, sync and async) to auto-record LLM spans with token usage and cost
- `AnthropicAdapter` — patches the Anthropic Python SDK (`messages.create`, sync and async) with a built-in pricing table covering all Claude models
- `LangGraphAdapter` — injects a LangChain callback handler into compiled LangGraph graphs to record node executions, LLM calls, and tool calls
- `CrewAIAdapter` — instruments a CrewAI `Crew` to capture `kickoff()` timing, per-agent tool calls, task completions, and inter-agent delegation spans

#### pytest plugin (`pytest-evalcraft`)
- Auto-registered via `entry_points` — zero-config activation when evalcraft is installed
- Fixtures: `capture_context`, `mock_llm`, `mock_tool`, `cassette`, `replay_engine`, `evalcraft_cassette_dir`
- Markers: `@pytest.mark.evalcraft_cassette(path)`, `@pytest.mark.evalcraft_capture(name, save)`, `@pytest.mark.evalcraft_agent`
- CLI options: `--cassette-dir DIR`, `--evalcraft-record {none,new,all}`
- Terminal summary: per-test agent run metrics table (tokens, cost, tools, latency, fingerprint) appended to pytest output

#### CLI (`evalcraft`)
- `evalcraft capture <script>` — run a Python script under capture and save the cassette
- `evalcraft replay <cassette>` — replay a cassette and display metrics (`--verbose` shows all spans)
- `evalcraft diff <old> <new>` — compare two cassettes side-by-side (`--json` for machine-readable output)
- `evalcraft eval <cassette>` — run assertions with `--max-cost`, `--max-tokens`, `--max-latency`, `--tool` flags; exits 1 on failure (CI-friendly)
- `evalcraft info <cassette>` — inspect cassette metadata, metrics, tool sequence, and spans (`--json` for raw JSON)
- `evalcraft mock <cassette>` — generate ready-to-use `MockLLM` and `MockTool` Python fixtures from a recorded cassette

#### Project infrastructure
- MIT license
- Python 3.9–3.13 support
- Optional dependency groups: `[pytest]`, `[openai]`, `[anthropic]`, `[langchain]`, `[crewai]`, `[all]`, `[dev]`
- Hatchling build system
- Ruff linting, mypy strict type checking, pytest-asyncio for async tests
- GitHub Actions CI and PyPI publish workflows
- 260 tests

[0.1.0]: https://github.com/beyhangl/evalcraft/releases/tag/v0.1.0

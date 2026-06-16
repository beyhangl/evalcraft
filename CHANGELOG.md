# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] — 2026-06-01

### Added
- **`evalcraft check-stale`** — activates the provenance every cassette already records (model set, prompt hash, timestamp) to flag deterministic tests that have silently gone stale: a recorded model absent from the current `--models` set is **CRITICAL** (non-zero exit — a CI gate), a drifted `--prompts` hash is a **WARNING**, and age is **INFO**. Adds a `StalenessChecker` Python API (`evalcraft.staleness`) and refactors a shared `compute_prompt_hash` so recorded and recomputed prompt hashes match byte-for-byte. No new dependencies; runs fully offline.

## [0.2.1] — 2026-05-30

### Fixed
- **Removed references to the unregistered `evalcraft.dev` domain.** The cloud client and the `evalcraft cloud` CLI no longer default to a non-existent `api.evalcraft.dev` endpoint. There is **no public hosted service** — configure a self-hosted dashboard URL explicitly via `base_url=`, the `EVALCRAFT_BASE_URL` env var, or `~/.evalcraft/config.json`. A cloud call with no URL configured now raises a clear, self-host-pointing error instead of failing against a dead host. Also scrubbed the dead domain from the `evalcraft init` config template and the landing-page contact links.

## [0.2.0] — 2026-05-30

Ships everything developed since the initial `0.1.0` PyPI upload — a much larger
evaluation surface, new drift-catching and determinism tooling, an honest
re-scope of the project's positioning, several bug fixes, and a full lint/type
cleanup. Backward-compatible with `0.1.0` cassettes.

### Added

#### Evaluation
- **LLM-as-Judge scorers** — `assert_output_semantic`, `assert_factual_consistency`, `assert_tone`, `assert_custom_criteria` (OpenAI or Anthropic judge, configurable model)
- **RAG metrics** — `assert_faithfulness`, `assert_context_relevance`, `assert_answer_relevance`, `assert_context_recall`
- **Pairwise A/B** — `pairwise_compare` and `pairwise_rank` (round-robin tournament) with position-bias mitigation
- **Statistical eval** — `eval_n` with Wilson-score confidence intervals
- **Multi-judge consensus** — `JuryScorer`
- **Hallucination detection** — `assert_no_hallucination`, `detect_hallucinations` (per-claim breakdown)
- **Live-eval mode** — `run_live_eval` / `compare_to_baseline` + the `evalcraft live-eval` CLI: run scorers against the *real* model over a golden input set and gate CI on score regressions. This is the layer that catches model/prompt/retrieval drift, which replay cannot.

#### Cassettes
- **Provenance metadata** — each recording captures the model set, a prompt hash, SDK/Python versions, and record time (for staleness reasoning); surfaced in `evalcraft info`. Loads provenance-less cassettes unchanged.
- **Opt-in judge cache** — `evalcraft.eval.judge_cache.use_judge_cache(...)` / the `EVALCRAFT_JUDGE_CACHE` env var record/replay LLM-judge responses for deterministic, $0 judge scoring in CI (modes: `auto` / `record` / `replay`).

#### Other
- Regression `TrendDetector` for multi-run gradual-drift analysis
- **Gemini** and **Pydantic AI** adapters (Python); Gemini + Vercel AI adapters (JS)
- `evalcraft generate-tests` (pytest file from a cassette) and `evalcraft doctor` (setup diagnostics)
- TypeScript/JavaScript SDK (pre-release, source-only): capture/replay, mocks, 16 scorers, OpenAI/Gemini/Vercel AI adapters

### Fixed
- LangGraph adapter: two `NameError`s in `on_llm_end` / `on_chain_end` (referenced callback params they never receive)
- NetworkGuard: Python 3.9/3.10 crash from hard-coding the `all_errors` kwarg (added to the stdlib only in 3.11) — now forwards `**kwargs`
- De-flaked the JS fingerprint-determinism test (pinned `Span.timestamp`)
- Repointed the dead `evalcraft.dev` documentation URL to the GitHub Pages site

### Changed
- **Positioning** re-scoped from "The pytest for AI agents" to **"VCR for AI agents"** — honest about what replay does, and no longer colliding with DeepEval's tagline
- Documentation corrected for accuracy: offline-vs-live scorer labeling, fingerprint/regression semantics (detects *recorded* changes, not live drift), an accurate Python-vs-JS parity matrix, a fact-checked comparison table, and JS install instructions (build-from-source; not yet on npm)

### Internal
- ruff: 325 → 0 findings; mypy: made runnable and clean across the package (strict bug-catching checks kept on; annotation-completeness sub-checks right-sized to the codebase's style)
- 803 Python tests and 145 JS tests passing

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

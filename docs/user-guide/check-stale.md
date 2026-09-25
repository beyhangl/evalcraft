# Check Stale — catch recordings that no longer mirror what you ship

A replayed cassette is a *deterministic* test: it passes as long as the recording
is unchanged. But that's exactly the trap — a green replay says nothing about
whether the recording still mirrors reality. In 2026, models get **hard
retirement dates** (and providers silently update weights). When the model a
cassette was recorded against is gone, your test keeps "passing" against a world
that no longer exists.

`evalcraft check-stale` fixes the blind spot by **activating the provenance**
every cassette already records (model set, prompt hash, timestamp) and turning it
into a CI gate.

```bash
evalcraft check-stale tests/cassettes/*.json --models "gpt-5.1,claude-sonnet-4-5"
```

```
  staleness check  3 cassette(s)

  refund_flow
  CRITICAL  [model_retired] Recorded model 'gpt-4o' is not in the current model set —
            it may have been retired or swapped. This deterministic test no longer
            mirrors production.
  fresh  weather_agent
  fresh  search_agent

  CRITICAL staleness found — re-record the affected cassettes
# exit code 1
```

## What it checks

| Finding | Severity | Meaning | Exits CI? |
|---|---|---|---|
| `reasoning_state_missing` | **CRITICAL** | Spans from a reasoning model carry no signed reasoning block, so replaying them is invalid. | **Yes (exit 1)** |
| `model_retired` | **CRITICAL** | A recorded model is absent from the current `--models` set (retired or swapped) — the cassette may now exercise an API that errors live. | **Yes (exit 1)** |
| `prompt_drift` | WARNING | The current prompt hash (`--prompts`) differs from the recorded one — still replays, but no longer mirrors the live prompt. | No |
| `tool_drift` | WARNING | A tool definition differs from `--tools`: added, removed, description changed, or parameters changed. The sharpest case is parameters that changed while the description did not. | No |
| `volatile_content` | WARNING | A UUID, timestamp or temp path generated at run time was recorded in what the agent sent. Always checked. | No |
| `model_alias_moved` | WARNING | Across the cassettes you pass, the same requested model id was served by different snapshots. Always checked. | No |
| `floating_model_alias` | INFO | The recording asked for a floating alias (`gpt-4o`, `*-latest`) rather than a pinned snapshot. | No |
| `age` | INFO | The recording is older than `--max-age-days`. | No |
| `no_provenance` | INFO | A legacy / hand-built cassette with no provenance — re-record to enable checks. | No |
| `no_tool_definitions` | INFO | `--tools` was given but the cassette predates tool recording (0.9). | No |

Only a **retired model** or **missing reasoning state** blocks the build. Those
are the signals that mean "your deterministic test is lying." Everything else is
visible but non-blocking.

## Flags

| Flag | Description |
|---|---|
| `--models "a,b,c"` | The model set you ship today. Any recorded model not in this exact set → CRITICAL. Omit to skip the model check. |
| `--prompts <file>` | A file of your current prompts; its hash is compared to the recorded `prompt_hash`. Omit to skip. |
| `--tools <file>` | The tool definitions your code ships today, as JSON. Each difference from the recorded definitions → WARNING. Omit to skip. |
| `--max-age-days N` | Recorded-at age over `N` days → INFO. Defaults to `30` if no other check is given. |
| `--json` | Emit `{"cassettes": [report, ...], "across_cassettes": [finding, ...]}` (severity strings `CRITICAL`/`WARNING`/`INFO`). Still exits 1 on any CRITICAL. |

Matching is **exact and case-sensitive** — a swap from `gpt-5.1` to `gpt-5.1-mini`
*should* fire. No fuzzy family matching. Cassettes recorded with 0.9 or later
are judged on the model id the code *asked for*. When it asked for an alias you
still list (`--models gpt-4o`) and the provider served a dated snapshot, nothing
is retired, and the `floating_model_alias` note covers it. Listing the snapshot
itself works too. Older cassettes only know the served model and keep exact
matching.

### `--prompts` file shape

The hash basis is identical to what was recorded at capture time, so a file that
reproduces the prompts matches byte-for-byte. Accepted shapes:

```jsonc
// 1. JSON object with the run's input + per-LLM-call inputs
{ "input_text": "refund order 123", "llm_inputs": ["system + user prompt...", "..."] }

// 2. JSON list → treated as llm_inputs (input_text = "")
["system + user prompt..."]

// 3. anything else → treated as input_text
```

## Tool definitions (`--tools`)

The model chooses a tool from its name and description. Change the parameters
and forget the description, and the model keeps calling the tool the old way.
Since 0.9 the OpenAI and Anthropic adapters record each tool's name, description
and a short hash of its parameter schema. `--tools` diffs them against what your
code ships now:

```bash
python -c "import json, myagent; print(json.dumps(myagent.TOOLS))" > tools.json
evalcraft check-stale tests/cassettes/*.json --tools tools.json
```

```
  WARNING   [tool_drift] tool 'search' parameters changed but its description did not;
            the model may keep calling it the old way
```

The file holds a list of tool definitions in OpenAI (`{"type": "function",
"function": {...}}`), OpenAI Responses (flat), Anthropic (`input_schema`) or MCP
(`inputSchema`) format, or an object with a `tools` list, so a saved request body
works as is. Everything besides the name and description counts as the schema,
including `strict` and a hosted tool's version. Only the OpenAI and Anthropic
adapters record tool definitions today.

## Run-time values in a recording

If the agent sends something generated fresh on every run, such as a request id,
the current time or a temporary path, the recording can't match a rerun. Mocks
generated with `evalcraft mock` key on the prompt, so they miss, and every
re-record churns the diff. `check-stale` scans what the agent *sent* (LLM inputs
and tool arguments, never outputs) for UUIDs, timestamps with a time of day and
temp paths, and warns. Content that was only passed along is skipped: tool
results and earlier assistant turns fed back into a prompt, and any value that
also shows up in a recorded output. An order id a tool returned is replayed data,
not a leak.

```
  WARNING   [volatile_content] Run-time values were recorded in what the agent sent:
            timestamp '2026-09-24T17:12:03Z' (llm input #1). ...
```

The fix is in the agent's test setup: inject a fixed clock, id factory or
directory. A bare date or a long number is never flagged, since those are
usually real content. The patterns are heuristics, so a fixed timestamp typed
into a prompt by hand will still be reported.

## Model aliases

Asking for `gpt-4o` gets you whichever snapshot the alias points at today. Since
0.9 the adapters record the id you asked for when the provider served a
different one. Each such recording gets an INFO `floating_model_alias`. When the
cassettes you check together (or a single cassette) show one id served by
different snapshots, you get a
WARNING `model_alias_moved` under "across cassettes": the model behind an
unchanged id changed between those recordings.

## Wire it into CI

Add it as a fast, deterministic gate next to your other checks — no API key, no
network:

```yaml
- name: Fail if any cassette was recorded against a retired model
  run: evalcraft check-stale tests/cassettes/*.json --models "${{ vars.CURRENT_MODELS }}"
```

When a model is retired, the gate goes red — **re-record the affected cassettes**
(which refreshes their provenance), review the new behavior, and commit.

## Python API

```python
from evalcraft import StalenessChecker
from evalcraft.core.models import Cassette

report = StalenessChecker(max_age_days=30).check(
    Cassette.load("tests/cassettes/refund_flow.json"),
    current_models=["gpt-5.1", "claude-sonnet-4-5"],
    current_tools=load_tool_definitions("tools.json"),  # optional
)
assert not report.has_critical, report.to_dict()
```

with `from evalcraft.core.tool_defs import load_tool_definitions`. For several
cassettes, `evalcraft.staleness.find_alias_moves([(label, cassette), ...])`
returns the cross-cassette `model_alias_moved` findings.

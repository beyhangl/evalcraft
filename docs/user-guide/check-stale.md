# Check Stale — catch cassettes recorded against a retired model

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
| `model_retired` | **CRITICAL** | A recorded model is absent from the current `--models` set (retired or swapped) — the cassette may now exercise an API that errors live. | **Yes (exit 1)** |
| `prompt_drift` | WARNING | The current prompt hash (`--prompts`) differs from the recorded one — still replays, but no longer mirrors the live prompt. | No |
| `age` | INFO | The recording is older than `--max-age-days`. | No |
| `no_provenance` | INFO | A legacy / hand-built cassette with no provenance — re-record to enable checks. | No |

Only a **retired model** blocks the build — it's the one signal that means "your
deterministic test is lying." Prompt drift and age are visible but non-blocking.

## Flags

| Flag | Description |
|---|---|
| `--models "a,b,c"` | The model set you ship today. Any recorded model not in this exact set → CRITICAL. Omit to skip the model check. |
| `--prompts <file>` | A file of your current prompts; its hash is compared to the recorded `prompt_hash`. Omit to skip. |
| `--max-age-days N` | Recorded-at age over `N` days → INFO. Defaults to `30` if no other check is given. |
| `--json` | Emit `{"cassettes": [report, ...]}` (severity strings `CRITICAL`/`WARNING`/`INFO`). Still exits 1 on any CRITICAL. |

Matching is **exact and case-sensitive** — a swap from `gpt-5.1` to `gpt-5.1-mini`
*should* fire. No fuzzy family matching.

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
)
assert not report.has_critical, report.to_dict()
```

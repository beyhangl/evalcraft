# Keeping recordings fresh

A recorded run is a snapshot of what the model did on the day you recorded it.
Nothing about a passing replay tells you whether that is still true. Left alone,
a suite of recordings turns into a record of old assumptions: every test green,
none of them about the model you ship today.

Evalcraft answers this with an **expiry policy** and a **one-command re-record**.
The policy is opt-in and lives in your repository, so CI and every developer
apply the same rule.

## Set a policy

```toml
# pyproject.toml
[tool.evalcraft]
expire_after_days = 90
```

From then on, a recording older than 90 days is *expired*:

| Where | What happens |
|---|---|
| `evalcraft check-stale` | CRITICAL `expired` finding, exit code 1 |
| `pytest` in CI (the `CI` variable is set) | A test that replays the cassette fails with "Cassette expired … re-record it" |
| `pytest` locally | The test runs and pytest shows an `EvalcraftExpiredCassetteWarning` |
| `pytest --evalcraft-record=new` | The cassette counts as missing and is recorded again |

Age comes from the time the cassette was recorded (its provenance), or its
`created_at` for cassettes made before provenance existed. A file with neither
can't be judged: `check-stale` gives it an `unknown_age` warning so it doesn't
pass unnoticed. The sample cassette `evalcraft init` writes is exempt.

In `--evalcraft-record=new`, an expired cassette behaves exactly like a missing
one: the `cassette` fixture returns `None` and the test is expected to run the
agent live and record. A replay-only test that can't record should skip on
`None`.

Pick a window shorter than your providers' deprecation notice. Some providers
now give as little as 45 days between a legacy notice and shutdown, so 90 days
is the longest window that makes sense for those models.

## Re-record what expired

```bash
# 1. Re-record expired and missing cassettes. Fresh ones are left alone.
pytest --evalcraft-record=new

# 2. See what changed.
git diff --stat tests/cassettes/
git show HEAD:tests/cassettes/refund_flow.json > /tmp/refund_flow.old.json
evalcraft diff /tmp/refund_flow.old.json tests/cassettes/refund_flow.json

# 3. Run the deterministic suite against the new recordings, then commit.
pytest
git add tests/cassettes/ && git commit -m "Re-record expired cassettes"
```

Step 2 is the point. A re-record is when a model update shows up as a changed
tool sequence, new arguments or a higher cost. Read the diff before you commit
it. Re-recording calls the real model and costs money, which is why it is always
a command you choose to run and never something a plain `pytest` does.

## The rest of the policy

The same table sets defaults for every `check-stale` option, so the CI step
doesn't need them spelled out:

```toml
[tool.evalcraft]
expire_after_days = 90                      # CRITICAL, fails CI
max_age_days = 30                           # INFO note, never fails
models = ["gpt-5.1", "claude-sonnet-4-5"]   # a recorded model not in this list is CRITICAL
tools = "tests/tools.json"                  # tool-definition drift is a WARNING
prompts = "tests/prompts.json"              # prompt drift is a WARNING
```

```yaml
- name: Cassettes still mirror what we ship
  run: evalcraft check-stale tests/cassettes/*.json
```

Paths are relative to `pyproject.toml`. Evalcraft reads the nearest
`pyproject.toml` that has a `[tool.evalcraft]` table, looking upwards from the
current directory (for `check-stale`) or the pytest root, but never past the
repository root.

Command-line flags override the table, for example `--expire-after-days 365` or
`pytest --evalcraft-expire-after-days 365`, and `0` switches the policy off for
one run. A wrong type is an error, so a bad value can't quietly switch the
policy off. An unknown key, such as a typo or an option from a newer evalcraft,
is reported as a warning.

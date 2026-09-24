# AGENTS.md

Guidance for coding agents working **on** the evalcraft codebase. If you are
*using* evalcraft to test an agent, read the bundled skill instead:
`evalcraft/.agents/skills/evalcraft/SKILL.md`.

## Commands

```bash
pip install -e ".[dev]"
pytest                      # full suite, no API keys or network needed
ruff check evalcraft tests
mypy evalcraft
```

All three must pass before a change is done. Tests never call a real model;
anything that would is mocked.

Build the docs into a scratch directory, never into the repo root:

```bash
mkdocs build -d /tmp/evalcraft-docs
```

`site/` is the hand-written landing page (logo, `index.html`, `CNAME`). A bare
`mkdocs build` writes to `./site` and destroys it.

## Rules that are easy to break

- **Never edit, delete or re-record a cassette or golden fixture to make a
  failing test pass.** Fix the code. If the recorded baseline genuinely needs
  updating, say so and leave it for a human to review in the diff.
- Scorers are split into **offline** (read the cassette only, no model call,
  $0, deterministic) and **live** (call a model, cost money). A new scorer in
  `eval/scorers/`, `eval/loops.py` or `eval/scorers/structured.py` must never
  call a model. Live scorers live in `eval/llm_judge.py`, `eval/rag_scorers.py`
  and friends, and the docs must say they cost money.
- Adapters record `prompt_tokens` as **fresh, uncached** input only. Cached
  input goes in `cache_read_tokens` / `cache_write_tokens` (see
  `core/models.py:TokenUsage`). OpenAI's `prompt_tokens` includes the cached
  portion and must be reduced by it.
- Coerce SDK usage fields with `_int_or_zero`; users mock SDK responses, and a
  `MagicMock` must never land in a cassette.
- Do not modify `.github/workflows/`, shell scripts or other CI/deploy config
  as part of a code change.

## Versioning and release

The version string appears in `pyproject.toml`, `evalcraft/__init__.py`,
`evalcraft/core/models.py` (`evalcraft_version`), `evalcraft/cloud/client.py`
(User-Agent), `evalcraft/cli/main.py` (`version_option`),
`evalcraft/.agents/skills/evalcraft/SKILL.md` (`metadata.version`) and
`tests/test_e2e_pipeline.py`. Bump all of them together; a test checks the
skill matches the package.

Update `CHANGELOG.md` and `docs/user-guide/changelog.md`. Publishing to PyPI
happens by pushing a `v*` tag; do not upload by hand.

## Layout

- `evalcraft/core/` — data model (`Cassette`, `Span`, `TokenUsage`), pricing,
  reasoning-state checks
- `evalcraft/capture/`, `evalcraft/replay/`, `evalcraft/mock/` — record, read
  back, and fake runs
- `evalcraft/eval/` — assertions (offline and live)
- `evalcraft/adapters/` — one module per agent SDK
- `evalcraft/staleness/` — `check-stale`
- `evalcraft/cli/` — the `evalcraft` command, including `init` templates
- `tests/test_onboarding.py`, `tests/test_examples.py` — the first-run path
  and every example must stay green

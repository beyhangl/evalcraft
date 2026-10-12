# Contributing to Evalcraft

Thanks for your interest! Here's everything you need to get started.

## Quick setup

Use Python 3.10 or newer for the `python3` command below.

```bash
git clone https://github.com/beyhangl/evalcraft
cd evalcraft
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
python -m pytest
```

The test suite uses fake SDKs and mocked responses. You do not need an API key,
a provider account, or paid model calls. Optional SDK tests skip when their
package is absent; install only the extra for the adapter you are changing.

## Your first contribution

1. Pick a small reproducible bug or a documentation correction. For a new
   integration, discuss a scoped issue before coding.
2. Run `python -m pytest tests/test_onboarding.py tests/test_examples.py` to
   verify the API-key-free first-run path.
3. Add a regression test with an in-memory response or fake tool. For Gemini,
   start with `tests/test_gemini_adapter.py`; its HTTP transport is mocked.
4. Fix the code and run the relevant test file, then the full checks below.
5. Explain the trigger, expected behavior, and commands you ran in the PR.

Never edit or re-record an existing cassette or golden fixture to make a test
pass. If a recorded baseline needs an intentional update, leave it unchanged
and describe the required human review in the PR. New tests can construct
synthetic inputs in memory without provider credentials.

## Before opening a PR

- **For bug fixes** — open a PR directly. Include a failing test that your fix resolves.
- **For new features** — open an issue first to discuss the approach. Significant changes without prior discussion may be declined.
- **For adapters** (OpenAI, LangChain, etc.) — new framework adapters are welcome; discuss in an issue first.

## Development workflow

```bash
# Format
ruff format path/to/changed_file.py

# Lint
ruff check evalcraft tests

# Type check
mypy evalcraft

# Run tests
pytest

# Run tests with coverage
pytest --cov=evalcraft --cov-report=term-missing
```

Run the full test suite, lint, and type checks before opening a PR. Format only
the files you changed. Reviewers will ask for all required checks to pass.

## Code conventions

- **Python 3.10+** — no syntax or stdlib features above 3.10 unless gated
- **Line length** — 100 characters (configured in `pyproject.toml`)
- **Types** — strict mypy; all public functions need type annotations
- **Tests** — every new feature or bug fix needs a test in `tests/`
- **Cassette fixtures** — test cassettes live in `tests/cassettes/`

## Adding a new framework adapter

1. Create `evalcraft/adapters/<framework>.py`
2. Add the optional dependency to `pyproject.toml` under `[project.optional-dependencies]`
3. Add mocked integration tests in `tests/test_<framework>_adapter.py`
4. Update the README framework support table

## Project structure

```
evalcraft/
├── core/          # Cassette, Span, data model
├── capture/       # CaptureContext and explicit tool capture
├── replay/        # Inspect and re-emit recorded spans
├── playback/      # Run changed code against recorded model responses
├── mock/          # MockLLM, MockTool
├── eval/          # Offline assertions and separate paid live scorers
├── adapters/      # SDK capture integrations
├── staleness/     # Cassette freshness and drift checks
├── cli/           # evalcraft CLI (click)
└── pytest_plugin/ # pytest fixtures and markers
tests/
├── cassettes/     # Fixture cassettes
└── ...
```

## Commit messages

Use conventional commits — `fix:`, `feat:`, `docs:`, `chore:`, `refactor:`. Keep the subject line under 72 chars.

## Releasing (maintainers only)

1. Bump `version` in `pyproject.toml`
2. Update the changelog
3. Tag: `git tag v0.x.y && git push --tags`
4. CI publishes to PyPI automatically on tag push

## License

By contributing you agree your code will be released under the [MIT License](LICENSE).

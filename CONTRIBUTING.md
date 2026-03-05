# Contributing to Evalcraft

Thanks for your interest! Here's everything you need to get started.

## Quick setup

```bash
git clone https://github.com/beyhangl/evalcraft
cd evalcraft
pip install -e ".[dev]"
pytest
```

## Before opening a PR

- **For bug fixes** — open a PR directly. Include a failing test that your fix resolves.
- **For new features** — open an issue first to discuss the approach. Significant changes without prior discussion may be declined.
- **For adapters** (OpenAI, LangChain, etc.) — new framework adapters are welcome; discuss in an issue first.

## Development workflow

```bash
# Format
ruff format .

# Lint
ruff check .

# Type check
mypy evalcraft/

# Run tests
pytest

# Run tests with coverage
pytest --cov=evalcraft --cov-report=term-missing
```

All three checks (format, lint, type check) must pass before a PR is merged. CI enforces this.

## Code conventions

- **Python 3.9+** — no syntax or stdlib features above 3.9 unless gated
- **Line length** — 100 characters (configured in `pyproject.toml`)
- **Types** — strict mypy; all public functions need type annotations
- **Tests** — every new feature or bug fix needs a test in `tests/`
- **Cassette fixtures** — test cassettes live in `tests/cassettes/`

## Adding a new framework adapter

1. Create `evalcraft/adapters/<framework>.py`
2. Add the optional dependency to `pyproject.toml` under `[project.optional-dependencies]`
3. Add integration tests under `tests/adapters/`
4. Update the README framework support table

## Project structure

```
evalcraft/
├── core/          # Cassette, Span, data model
├── capture.py     # CaptureContext
├── replay.py      # replay()
├── assertions.py  # assert_tool_called, assert_cost_under, etc.
├── mocks.py       # MockLLM, MockTool
├── adapters/      # OpenAI, LangChain, etc.
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

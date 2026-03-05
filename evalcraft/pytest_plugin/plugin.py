"""pytest-evalcraft — pytest plugin for testing AI agents.

Provides fixtures, markers, and terminal reporting for agent evaluation.

Fixtures:
    evalcraft_cassette_dir  — session-scoped Path for cassette storage
    capture_context         — function-scoped CaptureContext (active during test)
    mock_llm                — function-scoped MockLLM instance
    mock_tool               — factory fixture that creates MockTool instances
    cassette                — load a Cassette from @pytest.mark.evalcraft_cassette
    replay_engine           — load a ReplayEngine from @pytest.mark.evalcraft_cassette

Markers:
    @pytest.mark.evalcraft_cassette("tests/cassettes/foo.json")
        Path to cassette for replay-based tests.

    @pytest.mark.evalcraft_capture(name=None, save=True)
        Auto-capture this test's agent run and optionally save to cassette dir.

    @pytest.mark.evalcraft_agent
        Informational marker — tag tests as agent evaluation tests for filtering.

CLI options:
    --cassette-dir DIR       Where to store/load cassettes (default: tests/cassettes)
    --evalcraft-record MODE  none | new | all  (default: none)
                             none — replay-only; skip if cassette missing
                             new  — record cassettes that don't exist yet
                             all  — always re-record (overwrite existing)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Generator

import pytest

from evalcraft.capture.recorder import CaptureContext
from evalcraft.core.models import Cassette
from evalcraft.mock.llm import MockLLM
from evalcraft.mock.tool import MockTool
from evalcraft.replay.engine import ReplayEngine


# ─────────────────────────────────────────────────────
# Registration hooks
# ─────────────────────────────────────────────────────


def pytest_configure(config: pytest.Config) -> None:
    """Register markers and initialise session-level result store."""
    config.addinivalue_line(
        "markers",
        "evalcraft_cassette(path): path to cassette file for replay-based assertions",
    )
    config.addinivalue_line(
        "markers",
        "evalcraft_capture(name=None, save=True): capture agent run and save cassette",
    )
    config.addinivalue_line(
        "markers",
        "evalcraft_agent: tag test as an agent evaluation test",
    )
    # Session-level list accumulates per-test metrics for the terminal summary.
    config._evalcraft_results: list[dict] = []  # type: ignore[attr-defined]


def pytest_addoption(parser: pytest.Parser) -> None:
    """Add evalcraft CLI options to the pytest argument parser."""
    group = parser.getgroup("evalcraft", "Evalcraft agent testing options")
    group.addoption(
        "--cassette-dir",
        default=None,
        dest="cassette_dir",
        metavar="DIR",
        help="Directory to store/load cassettes (default: tests/cassettes)",
    )
    group.addoption(
        "--evalcraft-record",
        default="none",
        dest="evalcraft_record",
        choices=["none", "new", "all"],
        metavar="MODE",
        help=(
            "Cassette record mode: "
            "none=replay-only (skip if missing), "
            "new=record missing cassettes, "
            "all=always re-record"
        ),
    )


# ─────────────────────────────────────────────────────
# Session-scoped fixtures
# ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def evalcraft_cassette_dir(request: pytest.FixtureRequest) -> Path:
    """Return (and create) the cassette storage directory for this session.

    Override the path with ``--cassette-dir``.  Defaults to
    ``<rootdir>/tests/cassettes``.
    """
    option: str | None = request.config.getoption("cassette_dir", default=None)
    directory = Path(option) if option else Path(request.config.rootdir) / "tests" / "cassettes"
    directory.mkdir(parents=True, exist_ok=True)
    return directory


# ─────────────────────────────────────────────────────
# Function-scoped fixtures
# ─────────────────────────────────────────────────────


@pytest.fixture
def capture_context(request: pytest.FixtureRequest) -> Generator[CaptureContext, None, None]:
    """Provide an *active* CaptureContext for the duration of the test.

    All MockLLM / MockTool calls made inside the test are automatically
    recorded into ``capture_context.cassette``.

    When decorated with ``@pytest.mark.evalcraft_capture(save=True)`` (the
    default), the cassette is written to disk in ``evalcraft_cassette_dir``
    after the test finishes (even on failure).

    Example::

        @pytest.mark.evalcraft_capture(name="math_agent")
        def test_math(capture_context, mock_llm):
            mock_llm.add_response("*", "4")
            mock_llm.complete("What is 2+2?")
            assert capture_context.cassette.llm_call_count == 1
    """
    marker = request.node.get_closest_marker("evalcraft_capture")
    name = request.node.name
    save_path: Path | None = None

    if marker:
        # Allow positional or keyword name override.
        if marker.args:
            name = str(marker.args[0])
        elif "name" in marker.kwargs:
            name = str(marker.kwargs["name"])

        if marker.kwargs.get("save", True):
            cassette_dir: Path = request.getfixturevalue("evalcraft_cassette_dir")
            save_path = cassette_dir / f"{_safe_filename(name)}.json"

    ctx = CaptureContext(
        name=name,
        save_path=save_path,
        metadata={"pytest_node_id": request.node.nodeid},
    )
    with ctx:
        yield ctx

    # Store metrics for the terminal summary (runs even if test failed).
    _store_result(request.config, request.node.nodeid, ctx.cassette)


@pytest.fixture
def mock_llm() -> MockLLM:
    """Return a fresh :class:`~evalcraft.mock.llm.MockLLM` instance.

    The mock automatically records calls into the active
    :class:`~evalcraft.capture.recorder.CaptureContext` (if any).

    Example::

        def test_agent(mock_llm):
            mock_llm.add_response("What is 2+2?", "4")
            result = mock_llm.complete("What is 2+2?")
            assert result.content == "4"
    """
    return MockLLM()


@pytest.fixture
def mock_tool() -> Any:
    """Factory fixture for creating :class:`~evalcraft.mock.tool.MockTool` instances.

    Returns a callable — call it with the tool name to get a ``MockTool``.

    Example::

        def test_agent(mock_tool):
            search = mock_tool("web_search")
            search.returns({"results": [{"title": "Python"}]})
            result = search(query="Python tutorial")
            assert result["results"][0]["title"] == "Python"
    """

    def _factory(name: str, description: str = "") -> MockTool:
        return MockTool(name=name, description=description)

    return _factory


@pytest.fixture
def cassette(request: pytest.FixtureRequest) -> Cassette | None:
    """Load a :class:`~evalcraft.core.models.Cassette` from the path given in
    ``@pytest.mark.evalcraft_cassette``.

    Skips the test (or fails, depending on ``--evalcraft-record``) when the
    cassette file is not found.

    Example::

        @pytest.mark.evalcraft_cassette("tests/cassettes/search_agent.json")
        def test_replay(cassette):
            assert cassette.output_text == "Here are the results."
            assert cassette.tool_call_count == 1
    """
    return _load_cassette_from_marker(request)


@pytest.fixture
def replay_engine(request: pytest.FixtureRequest) -> ReplayEngine | None:
    """Load a :class:`~evalcraft.replay.engine.ReplayEngine` from the path given in
    ``@pytest.mark.evalcraft_cassette``.

    Skips the test when the cassette file is not found.

    Example::

        @pytest.mark.evalcraft_cassette("tests/cassettes/search_agent.json")
        def test_override_tool(replay_engine):
            replay_engine.override_tool_result("web_search", {"results": []})
            run = replay_engine.run()
            assert run.cassette.tool_call_count == 1
    """
    loaded = _load_cassette_from_marker(request)
    if loaded is None:
        return None
    return ReplayEngine(loaded)


# ─────────────────────────────────────────────────────
# Terminal reporting hook
# ─────────────────────────────────────────────────────


def pytest_terminal_summary(
    terminalreporter: Any,
    exitstatus: int,
    config: pytest.Config,
) -> None:
    """Append a compact agent-run metrics table to the terminal output."""
    try:
        results: list[dict] = config._evalcraft_results  # type: ignore[attr-defined]
    except AttributeError:
        return

    if not results:
        return

    terminalreporter.write_sep("=", "evalcraft agent run summary")

    for r in results:
        parts: list[str] = []
        if r["tokens"]:
            parts.append(f"tokens={r['tokens']}")
        if r["cost_usd"]:
            parts.append(f"cost=${r['cost_usd']:.4f}")
        if r["tool_calls"]:
            parts.append(f"tools={r['tool_calls']}")
        if r["llm_calls"]:
            parts.append(f"llm_calls={r['llm_calls']}")
        if r["duration_ms"]:
            parts.append(f"latency={r['duration_ms']:.0f}ms")
        if r["fingerprint"]:
            parts.append(f"fingerprint={r['fingerprint']}")

        info = ", ".join(parts) if parts else "no spans recorded"
        terminalreporter.write_line(f"  {r['node_id']}: {info}")

    total_tokens = sum(r["tokens"] for r in results)
    total_cost = sum(r["cost_usd"] for r in results)
    total_tools = sum(r["tool_calls"] for r in results)

    terminalreporter.write_line("")
    terminalreporter.write_line(
        f"  TOTAL: {len(results)} test(s) — "
        f"{total_tokens} tokens, "
        f"${total_cost:.4f} cost, "
        f"{total_tools} tool call(s)"
    )


# ─────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────


def _safe_filename(name: str) -> str:
    """Convert a test name / marker argument into a safe filesystem name."""
    for ch in r"""/\ []():;,"'""":
        name = name.replace(ch, "_")
    # Collapse repeated underscores
    while "__" in name:
        name = name.replace("__", "_")
    return name.strip("_")


def _load_cassette_from_marker(request: pytest.FixtureRequest) -> Cassette | None:
    """Resolve the cassette path from an ``evalcraft_cassette`` marker and load it.

    Returns ``None`` (after skipping) if the cassette is absent and the record
    mode permits it.  Raises ``pytest.fail`` for configuration errors.
    """
    marker = request.node.get_closest_marker("evalcraft_cassette")
    if marker is None:
        return None

    if not marker.args:
        pytest.fail(
            "@pytest.mark.evalcraft_cassette requires a path argument, "
            "e.g. @pytest.mark.evalcraft_cassette('tests/cassettes/my_test.json')"
        )

    path = Path(str(marker.args[0]))
    if not path.is_absolute():
        path = Path(str(request.config.rootdir)) / path

    if not path.exists():
        record_mode: str = request.config.getoption("evalcraft_record", default="none")
        if record_mode == "none":
            pytest.skip(
                f"Cassette not found: {path}  "
                f"(run with --evalcraft-record=new to record it)"
            )
        # For "new" / "all" modes the caller is responsible for live execution;
        # returning None signals "no recorded cassette available".
        return None

    return Cassette.load(path)


def _store_result(config: pytest.Config, node_id: str, cassette: Cassette) -> None:
    """Append per-test cassette metrics to the session result store."""
    cassette.compute_metrics()
    try:
        config._evalcraft_results.append(  # type: ignore[attr-defined]
            {
                "node_id": node_id,
                "name": cassette.name,
                "llm_calls": cassette.llm_call_count,
                "tool_calls": cassette.tool_call_count,
                "tokens": cassette.total_tokens,
                "cost_usd": cassette.total_cost_usd,
                "duration_ms": cassette.total_duration_ms,
                "fingerprint": cassette.fingerprint,
            }
        )
    except AttributeError:
        pass

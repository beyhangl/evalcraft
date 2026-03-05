"""pytest-evalcraft plugin package.

Registered automatically as a pytest plugin via the ``pytest11`` entry point
in ``pyproject.toml``::

    [project.entry-points.pytest11]
    evalcraft = "evalcraft.pytest_plugin.plugin"

The plugin provides fixtures, markers, and terminal reporting for
AI agent test suites.  See :mod:`evalcraft.pytest_plugin.plugin` for details.
"""

from evalcraft.pytest_plugin.plugin import (
    capture_context,
    cassette,
    evalcraft_cassette_dir,
    mock_llm,
    mock_tool,
    replay_engine,
    pytest_addoption,
    pytest_configure,
    pytest_terminal_summary,
)

__all__ = [
    "capture_context",
    "cassette",
    "evalcraft_cassette_dir",
    "mock_llm",
    "mock_tool",
    "replay_engine",
    "pytest_addoption",
    "pytest_configure",
    "pytest_terminal_summary",
]

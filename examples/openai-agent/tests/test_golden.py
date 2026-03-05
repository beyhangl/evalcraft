"""tests/test_golden.py — Golden-set regression test for the support agent.

Compares each cassette against the saved golden baseline.
Fails if tool sequences change, cost doubles, or tokens spike by 50%+.

Run:
    pytest tests/test_golden.py -v
"""

from __future__ import annotations

from pathlib import Path

import pytest
from evalcraft import GoldenSet, replay
from evalcraft.golden.manager import Thresholds

_HERE = Path(__file__).parent
GOLDEN_PATH = _HERE.parent / "golden" / "support_agent.golden.json"
CASSETTES_DIR = _HERE / "cassettes"


@pytest.fixture(scope="module")
def golden():
    if not GOLDEN_PATH.exists():
        pytest.skip(
            f"Golden set not found at {GOLDEN_PATH}. "
            "Run: python build_golden.py"
        )
    return GoldenSet.load(GOLDEN_PATH)


@pytest.mark.parametrize("scenario", ["order_tracking", "return_request", "damaged_item"])
def test_cassette_matches_golden(golden, scenario):
    """Each cassette must pass the golden-set comparison."""
    cassette_path = CASSETTES_DIR / f"{scenario}.json"
    if not cassette_path.exists():
        pytest.skip(f"Cassette not found: {cassette_path}")

    run = replay(cassette_path)
    result = golden.compare(run.cassette)

    assert result.passed, (
        f"Golden regression for '{scenario}':\n{result.summary()}"
    )


def test_golden_metadata(golden):
    """Sanity-check the golden set structure."""
    assert golden.name == "support_agent_v1"
    assert golden.version >= 1
    assert golden.cassette_count >= 1

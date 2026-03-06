"""Auto-detect regressions when a new cassette is uploaded."""

from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from evalcraft.core.models import Cassette as CoreCassette
from evalcraft.golden.manager import GoldenSet as CoreGoldenSet
from evalcraft.regression.detector import RegressionDetector, Severity

from app.models.golden_set import StoredGoldenSet
from app.models.regression import RegressionEvent


async def check_regressions(
    cassette_raw: dict,
    project_id: uuid.UUID,
    cassette_id: uuid.UUID,
    db: AsyncSession,
) -> list[RegressionEvent]:
    """Run regression detection for a newly uploaded cassette.

    Finds all golden sets for the project, runs the core detector
    against each, and stores any regression events found.
    """
    result = await db.execute(
        select(StoredGoldenSet).where(StoredGoldenSet.project_id == project_id)
    )
    golden_sets = result.scalars().all()

    if not golden_sets:
        return []

    candidate = CoreCassette.from_dict(cassette_raw)
    candidate.compute_metrics()
    detector = RegressionDetector()

    events: list[RegressionEvent] = []

    for gs_row in golden_sets:
        core_gs = CoreGoldenSet.from_dict(gs_row.raw_data)
        golden = core_gs.get_primary_cassette()
        if golden is None:
            continue

        report = detector.compare(golden, candidate)
        for reg in report.regressions:
            event = RegressionEvent(
                project_id=project_id,
                cassette_id=cassette_id,
                golden_set_id=gs_row.id,
                severity=reg.severity.value,
                category=reg.category,
                message=reg.message,
                details={
                    "golden_value": _safe_serialize(reg.golden_value),
                    "current_value": _safe_serialize(reg.current_value),
                },
            )
            db.add(event)
            events.append(event)

    if events:
        await db.flush()

    return events


def _safe_serialize(value: object) -> object:
    """Ensure a value is JSON-serializable."""
    if isinstance(value, (str, int, float, bool, type(None))):
        return value
    if isinstance(value, (list, tuple)):
        return [_safe_serialize(v) for v in value]
    if isinstance(value, dict):
        return {k: _safe_serialize(v) for k, v in value.items()}
    return str(value)

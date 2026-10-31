"""Fixtures: bundles built from REAL organizer-generator records (seeded), ingested for real."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import pytest

from netcoop.core.bus import MessageBus
from netcoop.core.ids import FixedClock, IdFactory
from netcoop.core.log_store import LogStore
from netcoop.ingestion.models import NormalizedBundle
from netcoop.ingestion.normalize import ingest
from netcoop.scenarios.generator import load_generator
from netcoop.tools.toolbox import ToolBox
from netcoop.tools.topology import load_topology

T0 = datetime(2026, 10, 31, 12, tzinfo=UTC)
GEN = load_generator()


def generator_bundle(
    faults: dict[str, str] | None = None,
    *,
    samples: int = 3,
    drop_metrics: dict[str, list[str]] | None = None,
    topology: bool = True,
) -> NormalizedBundle:
    """10 devices x `samples` timestamps; device -> fault profile overrides."""
    faults = faults or {}
    records: list[dict[str, Any]] = []
    seed = 0
    for k in range(samples):
        for n in range(1, 11):
            device = f"SW_CAMPUS_{n}"
            seed += 1
            rec = GEN.generate(
                faults.get(device, "normal"), seed=seed, at=T0 + timedelta(minutes=5 * k)
            )
            rec["device_id"] = device  # generator picks a random id; scenarios pin it
            for m in (drop_metrics or {}).get(device, []):
                rec["metrics"].pop(m, None)
            records.append(rec)
    raw: dict[str, Any] = {"records": records, "provenance": "synthetic-generator"}
    if topology:
        raw["topology_ref"] = "campus_v1"
    result = ingest(json.dumps(raw))
    assert result.bundle is not None
    return result.bundle


@pytest.fixture
def make_bus(tmp_path: Path) -> Callable[[], MessageBus]:
    def _make() -> MessageBus:
        return MessageBus(LogStore(tmp_path / "log.sqlite3"), clock=FixedClock(T0), ids=IdFactory())

    return _make


def toolbox_for(bundle: NormalizedBundle, *, topology: bool = True) -> ToolBox:
    return ToolBox(bundle, load_topology("campus_v1") if topology else None, clock=FixedClock(T0))

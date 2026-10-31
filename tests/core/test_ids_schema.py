"""Deterministic ids/clock and the committed JSON Schema contract (T-PROTO-SCHEMA-01)."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from netcoop.core.ids import FixedClock, IdFactory, SystemClock
from netcoop.core.messages import PAYLOAD_TYPES
from netcoop.core.schema_export import SCHEMA_DIR, export_schemas


def test_ids_are_sequential_per_kind() -> None:
    ids = IdFactory()
    assert ids.incident() == "INC-0001"
    assert ids.incident() == "INC-0002"
    assert ids.message() == "MSG-000001"
    assert ids.next("OBS") == "OBS-0001"
    assert IdFactory().incident() == "INC-0001"  # fresh factory restarts: replayable


def test_fixed_clock_steps() -> None:
    start = datetime(2026, 10, 31, tzinfo=UTC)
    clock = FixedClock(start, step=timedelta(seconds=1))
    assert clock.now() == start
    assert clock.now() == start + timedelta(seconds=1)


def test_system_clock_is_utc_aware() -> None:
    assert SystemClock().now().tzinfo is not None


def test_committed_schemas_are_current(tmp_path: Path) -> None:
    written = export_schemas(tmp_path)
    names = {p.name for p in written}
    assert names == {"envelope.schema.json"} | {f"{t}.schema.json" for t in PAYLOAD_TYPES}
    for p in written:
        committed = SCHEMA_DIR / p.name
        assert committed.exists(), f"run `uv run python -m netcoop.core.schema_export` ({p.name})"
        assert json.loads(committed.read_text("utf-8")) == json.loads(p.read_text("utf-8")), (
            f"{p.name} is stale; re-export"
        )

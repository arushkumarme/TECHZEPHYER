"""Data snapshot ID: a fingerprint of exactly the data every agent analyses (Prompt 2)."""

from __future__ import annotations

import json
import math
from datetime import UTC, datetime

import pytest

from netcoop.config.settings import load_settings
from netcoop.core.ids import FixedClock
from netcoop.core.snapshot import (
    CanonicalHashError,
    canonical_hash,
    canonical_json,
    take_snapshot,
)
from netcoop.diagnosis.params import load_diagnosis_params
from netcoop.ingestion.normalize import ingest
from netcoop.scenarios.runner import load_scenario
from netcoop.tools.topology import load_topology

T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)


def _bundle(raw: bytes):  # type: ignore[no-untyped-def]
    result = ingest(raw)
    assert result.bundle is not None
    return result.bundle


def _snap(raw: bytes, *, topology: bool = True):  # type: ignore[no-untyped-def]
    return take_snapshot(
        _bundle(raw),
        load_topology("campus_v1") if topology else None,
        settings=load_settings(),
        params=load_diagnosis_params(),
        source_label="test",
        clock=FixedClock(T0),
    )


def test_canonical_json_is_order_independent_and_strict() -> None:
    assert canonical_json({"b": 1, "a": [2, 3]}) == canonical_json({"a": [2, 3], "b": 1})
    assert canonical_json({"a": "é"}) == '{"a":"é"}'
    with pytest.raises(CanonicalHashError):
        canonical_json({"x": math.nan})
    with pytest.raises(CanonicalHashError):
        canonical_json({"x": math.inf})
    assert len(canonical_hash({"a": 1})) == 64


def test_same_data_in_a_different_key_order_gives_the_same_snapshot() -> None:
    raw = load_scenario("S-02").input_bytes
    doc = json.loads(raw)
    reordered = {k: doc[k] for k in reversed(list(doc))}
    reordered["records"] = [{k: r[k] for k in reversed(list(r))} for r in doc["records"]]
    a, b = _snap(raw), _snap(json.dumps(reordered).encode())
    assert a.snapshot_id == b.snapshot_id and a.bundle_hash == b.bundle_hash


def test_changing_one_value_changes_the_snapshot() -> None:
    raw = load_scenario("S-02").input_bytes
    doc = json.loads(raw)
    doc["records"][0]["metrics"]["latency_ms"] += 0.01
    assert _snap(raw).snapshot_id != _snap(json.dumps(doc).encode()).snapshot_id


def test_snapshot_descriptor_contents() -> None:
    s = _snap(load_scenario("S-02").input_bytes)
    assert s.snapshot_id.startswith("SNAP-") and len(s.snapshot_id) == 17
    assert s.snapshot_id == "SNAP-" + s.bundle_hash[:12]
    assert s.mode == "simulation"
    assert s.data_provenance == "synthetic-generator"
    assert s.bundle_acceptance == "READY"
    assert len(s.topology_version) == 12 and len(s.config_hash) == 12
    assert s.created_at == T0
    assert _snap(load_scenario("S-02").input_bytes, topology=False).topology_version == "none"


def test_unregistered_provenance_is_kept_but_not_stamped() -> None:
    doc = json.loads(load_scenario("S-01").input_bytes)
    doc["provenance"] = "some-lab-export"
    s = _snap(json.dumps(doc).encode())
    assert s.data_provenance == "unspecified"
    assert s.declared_provenance == "some-lab-export"

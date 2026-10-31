"""Ingestion, validation and normalization (doc 05 §6; doc 09 §5 E-01..E-12).

Records built here are SYNTHETIC TEST FIXTURES in the generator's layout; real generator
output is exercised in ``test_ingest_generator_bundle``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from netcoop.ingestion.normalize import ingest
from netcoop.scenarios.generator import load_generator

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
NORMAL_METRICS = {
    "cpu_utilization_pct": 20.0,
    "link_utilization_pct": 30.0,
    "packet_loss_pct": 0.0,
    "latency_ms": 10.0,
    "jitter_ms": 2.0,
    "queue_drops": 0,
}


def rec(
    device: str = "SW_CAMPUS_1",
    minutes: float = 0,
    status: str = "Healthy",
    **metrics: Any,
) -> dict[str, Any]:
    m = dict(NORMAL_METRICS)
    for k, v in metrics.items():
        if v is None:
            m.pop(k, None)
        else:
            m[k] = v
    return {
        "timestamp": (T0 + timedelta(minutes=minutes)).isoformat().replace("+00:00", "Z"),
        "device_id": device,
        "metrics": m,
        "status": status,
    }


def codes(result: Any) -> set[str]:
    return {i.code for i in result.issues}


def state(result: Any, entity: str, metric: str) -> tuple[str, str | None]:
    s = result.bundle.metric_states[(entity, metric)]
    return s.assessability, s.reason


# ---------------------------------------------------------------- happy path


def test_ingest_generator_bundle() -> None:  # T-ING-GEN-01: real generator output
    gen = load_generator()
    records = [gen.generate("normal", seed=i, at=T0 + timedelta(minutes=i)) for i in range(10)]
    result = ingest(json.dumps({"records": records, "provenance": "synthetic-generator"}))
    assert result.acceptance == "READY", [i.code for i in result.issues]
    b = result.bundle
    assert b is not None
    assert b.provenance == "synthetic-generator"
    assert set(b.entities) == {r["device_id"] for r in records}
    # interface_errors is never produced by the normal profile: not assessable, not healthy.
    for entity in b.entities:
        assert state(result, entity, "interface_errors") == ("not_assessable", "MISSING")
        assert state(result, entity, "latency_ms") == ("assessed", None)
    assert "METRIC_NOT_PROVIDED" in codes(result)
    assert b.data_quality.completeness == pytest.approx(7 / 8)
    assert b.window.start == T0


def test_bare_array_is_accepted() -> None:
    result = ingest(json.dumps([rec()]))
    assert result.acceptance == "READY"
    assert result.bundle is not None and result.bundle.provenance == "unspecified"


# ---------------------------------------------------------------- rejections


def test_e01_unparseable() -> None:
    r = ingest("{not json")
    assert (r.acceptance, r.rejection_code) == ("REJECTED", "INPUT_UNPARSEABLE")
    assert r.bundle is None


def test_e01_wrong_top_level_type() -> None:
    assert ingest('"hello"').rejection_code == "INPUT_UNPARSEABLE"
    assert ingest('{"records": 5}').rejection_code == "INPUT_UNPARSEABLE"


def test_e02_unsupported_schema_major() -> None:
    r = ingest(json.dumps({"schema_version": "3.0", "records": [rec()]}))
    assert r.rejection_code == "INPUT_SCHEMA_VERSION_UNSUPPORTED"


def test_e02_flat_layout_adapter() -> None:
    flat = {"timestamp": "2026-10-31T12:00:00Z", "device_id": "SW_CAMPUS_2", **NORMAL_METRICS}
    flat["status"] = "Healthy"
    r = ingest(json.dumps({"schema_version": "0.9", "records": [flat]}))
    assert r.acceptance == "READY_WITH_WARNINGS"
    assert "SCHEMA_ADAPTER_APPLIED" in codes(r)
    assert state(r, "SW_CAMPUS_2", "latency_ms") == ("assessed", None)


def test_no_entity_rejected() -> None:
    bad = rec()
    del bad["device_id"]
    assert ingest(json.dumps([bad])).rejection_code == "INPUT_NO_ENTITY"
    assert ingest(json.dumps({"records": []})).rejection_code == "INPUT_NO_ENTITY"


def test_e09_all_timestamps_unusable_rejected() -> None:
    a, b = rec(), rec("SW_CAMPUS_2")
    a["timestamp"] = "yesterday"
    del b["timestamp"]
    assert ingest(json.dumps([a, b])).rejection_code == "INPUT_NO_TIMESTAMP"


def test_e09_some_timestamps_unusable_flagged() -> None:
    a, b = rec(), rec("SW_CAMPUS_2")
    b["timestamp"] = "2026-10-31T12:00:00"  # naive: timezone unknown -> not guessed
    r = ingest(json.dumps([a, b]))
    assert r.acceptance == "READY_WITH_WARNINGS"
    assert "TIMESTAMP_UNUSABLE" in codes(r)
    assert r.bundle is not None and "SW_CAMPUS_2" not in r.bundle.entities


def test_no_usable_metric_rejected() -> None:
    r = ingest(json.dumps([{"timestamp": "2026-10-31T12:00:00Z", "device_id": "X", "metrics": {}}]))
    assert r.rejection_code == "INPUT_NO_USABLE_METRIC"


def test_live_mode_refused() -> None:
    r = ingest(json.dumps({"mode": "live", "records": [rec()]}))
    assert r.rejection_code == "INPUT_MODE_UNSUPPORTED"


# ---------------------------------------------------------------- degraded but usable


def test_e03_unknown_record_field_ignored_and_logged() -> None:
    x = rec()
    x["site"] = "lab"
    r = ingest(json.dumps([x]))
    assert r.acceptance == "READY"
    assert "FIELD_IGNORED" in codes(r)


def test_e04_alias_applied() -> None:
    x = rec(latency_ms=None)
    x["metrics"]["latency_s"] = 0.25
    x["deviceId"] = x.pop("device_id")
    r = ingest(json.dumps([x]))
    assert "FIELD_ALIAS_APPLIED" in codes(r)
    assert "UNIT_CONVERTED" in codes(r)
    assert r.bundle is not None
    assert r.bundle.records[0].metrics["latency_ms"] == pytest.approx(250.0)


def test_e05_unmapped_field_makes_metric_not_assessable() -> None:
    x = rec(latency_ms=None)
    x["metrics"]["lat_val"] = 12
    r = ingest(json.dumps([x]))
    assert "FIELD_UNMAPPED" in codes(r)
    assert state(r, "SW_CAMPUS_1", "latency_ms") == ("not_assessable", "UNMAPPED_FIELD")


def test_e06_declared_unit_converted() -> None:
    x = rec(link_utilization_pct=None)
    x["metrics"]["link_util_ratio"] = 0.94
    r = ingest(json.dumps([x]))
    assert r.bundle is not None
    assert r.bundle.records[0].metrics["link_utilization_pct"] == pytest.approx(94.0)
    conv = [c for c in r.issues if c.code == "UNIT_CONVERTED"]
    assert conv and conv[0].severity == "info"


def test_e07_ambiguous_unit_not_assessable() -> None:
    x = rec(latency_ms=None)
    x["metrics"]["latency"] = 0.25  # alias without unit, no declaration
    r = ingest(json.dumps([x]))
    assert "UNIT_AMBIGUOUS" in codes(r)
    assert state(r, "SW_CAMPUS_1", "latency_ms") == ("not_assessable", "UNIT_AMBIGUOUS")


def test_e07_declared_unit_resolves_alias() -> None:
    x = rec(latency_ms=None)
    x["metrics"]["latency"] = 0.25
    x["units"] = {"latency": "s"}
    r = ingest(json.dumps([x]))
    assert r.bundle is not None
    assert r.bundle.records[0].metrics["latency_ms"] == pytest.approx(250.0)


def test_e07_contradicting_declaration_is_ambiguous() -> None:
    x = rec()
    x["units"] = {"latency_ms": "s"}  # name says ms, declaration says s -> not guessed
    r = ingest(json.dumps([x]))
    assert state(r, "SW_CAMPUS_1", "latency_ms") == ("not_assessable", "UNIT_AMBIGUOUS")


def test_e08_metric_missing_for_some_entities() -> None:  # T-ERR-MISSING-01
    r = ingest(json.dumps([rec("SW_CAMPUS_1"), rec("SW_CAMPUS_2", jitter_ms=None)]))
    assert r.acceptance == "READY_WITH_WARNINGS"
    assert "METRIC_MISSING" in codes(r)
    assert state(r, "SW_CAMPUS_2", "jitter_ms") == ("not_assessable", "MISSING")
    assert state(r, "SW_CAMPUS_1", "jitter_ms") == ("assessed", None)


def test_e10_stale_entity_gets_caveat() -> None:
    r = ingest(json.dumps([rec("SW_CAMPUS_1", minutes=60), rec("SW_CAMPUS_2", minutes=0)]))
    assert "DATA_STALE" in codes(r)
    assert state(r, "SW_CAMPUS_2", "latency_ms") == ("assessed_with_caveat", "STALE")
    assert state(r, "SW_CAMPUS_1", "latency_ms") == ("assessed", None)
    assert r.bundle is not None and r.bundle.data_quality.freshness == pytest.approx(0.5)


def test_e10_reference_time_makes_everything_stale() -> None:
    r = ingest(json.dumps({"reference_time": "2026-11-01T12:00:00Z", "records": [rec()]}))
    assert state(r, "SW_CAMPUS_1", "cpu_utilization_pct") == ("assessed_with_caveat", "STALE")


def test_e11_implausible_value() -> None:
    r = ingest(json.dumps([rec(cpu_utilization_pct=180.0)]))
    assert "VALUE_IMPLAUSIBLE" in codes(r)
    assert state(r, "SW_CAMPUS_1", "cpu_utilization_pct") == ("not_assessable", "IMPLAUSIBLE")
    assert r.bundle is not None
    assert "cpu_utilization_pct" not in r.bundle.records[0].metrics


def test_malformed_value() -> None:
    r = ingest(json.dumps([rec(latency_ms="fast"), rec("SW_CAMPUS_2", queue_drops=True)]))
    assert state(r, "SW_CAMPUS_1", "latency_ms") == ("not_assessable", "MALFORMED")
    assert state(r, "SW_CAMPUS_2", "queue_drops") == ("not_assessable", "MALFORMED")


def test_unknown_status_is_not_healthy() -> None:
    r = ingest(json.dumps([rec(status="UP"), rec("SW_CAMPUS_2", status="critical")]))
    assert state(r, "SW_CAMPUS_1", "status") == ("not_assessable", "MALFORMED")
    assert r.bundle is not None
    statuses = {x.entity: x.status for x in r.bundle.records}
    assert statuses == {"SW_CAMPUS_1": None, "SW_CAMPUS_2": "Critical"}


def test_e12_duplicates_removed_and_conflicts_kept() -> None:
    a = rec()
    conflicting = rec(latency_ms=300.0)
    r = ingest(json.dumps([a, dict(a), conflicting]))
    assert "RECORD_DUPLICATE" in codes(r)
    assert "RECORD_CONFLICT" in codes(r)
    assert r.bundle is not None and len(r.bundle.records) == 2


def test_probes_are_validated_and_labelled() -> None:
    probes = [
        {
            "probe_id": "P1",
            "from_entity": "SW_CAMPUS_1",
            "service": "dns",
            "outcome": "timeout",
            "timestamp": "2026-10-31T12:00:00Z",
        },
        {"probe_id": "P2", "service": "ntp", "outcome": "ok"},
    ]
    r = ingest(json.dumps({"records": [rec()], "probes": probes}))
    assert r.bundle is not None
    assert [p.probe_id for p in r.bundle.probes] == ["P1"]
    assert r.bundle.probes[0].provenance == "team-authored probe"
    assert "PROBE_INVALID" in codes(r)


def test_record_ids_trace_to_raw_index() -> None:
    r = ingest(json.dumps([rec(), rec("SW_CAMPUS_2")]))
    assert r.bundle is not None
    assert [(x.record_id, x.source_index) for x in r.bundle.records] == [
        ("REC-0001", 0),
        ("REC-0002", 1),
    ]


@settings(max_examples=60, deadline=None)
@given(
    drop=st.lists(st.sampled_from(sorted(NORMAL_METRICS)), unique=True),
    corrupt=st.lists(st.sampled_from(sorted(NORMAL_METRICS)), unique=True),
)
def test_missing_or_broken_is_never_assessed(drop: list[str], corrupt: list[str]) -> None:
    """T-ERR-MISSING-02 (property): a metric absent or corrupted is never 'assessed'."""
    overrides: dict[str, Any] = {m: None for m in drop}
    overrides.update({m: "garbage" for m in corrupt if m not in drop})
    r = ingest(json.dumps([rec(**overrides)]))
    if r.bundle is None:
        assert set(drop) | set(corrupt) >= set(NORMAL_METRICS)
        return
    for m in set(drop) | set(corrupt):
        assert r.bundle.metric_states[("SW_CAMPUS_1", m)].assessability == "not_assessable"

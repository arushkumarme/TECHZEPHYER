"""Scenario packages S-01..S-12 (doc 09 §2-§3), built deterministically.

Every input is built from the organizer generator with fixed seeds and a fixed clock;
team-authored variants then *mutate* that output (doc 05 §6.4) and say so in their
metadata. ``scripts/build_scenarios.py`` writes them to ``sample_data/scenarios/``; a test
regenerates them and requires byte-identical files, so inputs are frozen AND reproducible.

Ground truth is "by construction" (doc 09 §3): the generator labels only its own
``fault_type`` argument; the expected outcomes below are our documented interpretation.
"""

from __future__ import annotations

import copy
import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from netcoop.scenarios.generator import load_generator

T0 = datetime(2026, 10, 31, 12, 0, tzinfo=UTC)
DEVICES = [f"SW_CAMPUS_{n}" for n in range(1, 11)]
SAMPLES = 3
STEP = timedelta(minutes=5)

Records = list[dict[str, Any]]


def base_records(faults: dict[str, str] | None = None, *, seed_base: int = 0) -> Records:
    """10 devices x 3 timestamps from the organizer generator (device ids pinned)."""
    gen = load_generator()
    faults = faults or {}
    out: Records = []
    seed = seed_base
    for k in range(SAMPLES):
        for device in DEVICES:
            seed += 1
            rec = gen.generate(faults.get(device, "normal"), seed=seed, at=T0 + STEP * k)
            rec["device_id"] = device  # the generator draws a random id; scenarios pin it
            out.append(rec)
    return out


def _bundle(records: Records, provenance: str, **extra: Any) -> dict[str, Any]:
    return {"records": records, "provenance": provenance, "topology_ref": "campus_v1", **extra}


def _for(records: Records, device: str) -> Records:
    return [r for r in records if r["device_id"] == device]


# --------------------------------------------------------------------------- builders


def s01() -> dict[str, Any]:
    return _bundle(base_records(), "synthetic-generator")


def s02() -> dict[str, Any]:
    return _bundle(base_records({"SW_CAMPUS_4": "latency_spike"}), "synthetic-generator")


def s03() -> dict[str, Any]:
    recs = base_records(seed_base=300)
    for i, r in enumerate(_for(recs, "SW_CAMPUS_5")):
        r["metrics"]["wifi_signal_dbm"] = [-81, -84, -86][i]  # no mapping exists: not guessed
        r["metrics"]["packet_loss_pct"] = [0.6, 0.9, 1.2][i]
    return _bundle(recs, "team-authored")


def s04() -> dict[str, Any]:
    recs = base_records(seed_base=400)
    for i, r in enumerate(_for(recs, "SW_CAMPUS_6")):
        r["metrics"]["interface_errors"] = [40, 120, 260][i]  # rising
        r["metrics"]["packet_loss_pct"] = [1.5, 4.0, 8.5][i]
        r["status"] = "Warning"
    return _bundle(recs, "team-authored")


def s05() -> dict[str, Any]:
    recs = base_records(seed_base=500)
    probes = [
        {
            "probe_id": f"DNS-{i + 1}",
            "from_entity": "SW_CAMPUS_4",
            "service": "dns",
            "outcome": outcome,
            "response_ms": None,
            "timestamp": (T0 + STEP * i).isoformat().replace("+00:00", "Z"),
        }
        for i, outcome in enumerate(["timeout", "failure", "timeout"])
    ] + [
        {
            "probe_id": "DNS-OK-1",
            "from_entity": "SW_CAMPUS_7",
            "service": "dns",
            "outcome": "success",
            "response_ms": 12.0,
            "timestamp": T0.isoformat().replace("+00:00", "Z"),
        }
    ]
    return _bundle(recs, "synthetic-generator + team-authored probes", probes=probes)


def s06() -> dict[str, Any]:
    recs = base_records(seed_base=600)
    for r in recs:
        m = r["metrics"]
        r["deviceId"] = r.pop("device_id")  # listed alias
        m["cpu_pct"] = m.pop("cpu_utilization_pct")  # listed alias with unit
        m["latency_s"] = round(m.pop("latency_ms") / 1000, 5)  # listed alias, unit converted
        m["lat_jitter"] = m.pop("jitter_ms")  # NO alias -> unmapped, not assessable
        m["drops"] = m.pop("queue_drops")  # listed alias
        m["link_util"] = m.pop("link_utilization_pct")  # NO alias -> unmapped
    return _bundle(recs, "team-authored", schema_version="1.3")


def s06b() -> dict[str, Any]:
    return _bundle(base_records(seed_base=650), "team-authored", schema_version="2.0")


def s07() -> dict[str, Any]:
    recs = base_records({"SW_CAMPUS_4": "latency_spike"})
    for r in _for(recs, "SW_CAMPUS_4"):
        r["metrics"].pop("queue_drops")
    for r in _for(recs, "SW_CAMPUS_8"):
        r["metrics"].pop("cpu_utilization_pct")
    return _bundle(recs, "team-authored")


def s08() -> dict[str, Any]:
    recs = base_records({"SW_CAMPUS_4": "latency_spike"})
    for r in _for(recs, "SW_CAMPUS_4"):
        for k in ("link_utilization_pct", "queue_drops", "jitter_ms", "cpu_utilization_pct"):
            r["metrics"].pop(k)
        r.pop("status")
    return _bundle(recs, "team-authored")


def s09() -> dict[str, Any]:
    recs = base_records(seed_base=900)
    for r in _for(recs, "SW_CAMPUS_4"):
        r["metrics"].update(interface_errors=250, packet_loss_pct=12.0)
    for r in _for(recs, "SW_CAMPUS_6"):
        r["metrics"].update(cpu_utilization_pct=97.0, latency_ms=180.0, queue_drops=40)
    return _bundle(recs, "team-authored")


def s10() -> dict[str, Any]:
    return s02()


def s11() -> dict[str, Any]:
    b = s02()
    b.pop("topology_ref")
    return b


def s12() -> dict[str, Any]:
    recs = base_records(seed_base=1200)
    # Conflicting duplicate for SW_CAMPUS_3 at the last timestamp (same time, different value).
    last = _for(recs, "SW_CAMPUS_3")[-1]
    twin = copy.deepcopy(last)
    twin["metrics"]["latency_ms"] = 310.0
    recs.append(twin)
    # SW_CAMPUS_9 reports only old data (stale): shift its records back by 2 hours.
    for r in _for(recs, "SW_CAMPUS_9"):
        t = datetime.fromisoformat(r["timestamp"].replace("Z", "+00:00")) - timedelta(hours=2)
        r["timestamp"] = t.isoformat().replace("+00:00", "Z")
    return _bundle(recs, "team-authored")


# --------------------------------------------------------------------------- catalogue

SCENARIOS: dict[str, dict[str, Any]] = {
    "S-01": {
        "title": "Normal operation",
        "pdf_scenario": "Normal network operation",
        "build": s01,
        "description": "All ten devices from the generator `normal` profile.",
        "expected": {"status": ["no_fault_detected"], "affected_devices": []},
    },
    "S-02": {
        "title": "Link congestion (generator latency_spike)",
        "pdf_scenario": "Link congestion",
        "build": s02,
        "description": "SW_CAMPUS_4 from the generator `latency_spike` profile: elevated "
        "utilization and queue drops with high latency/jitter. Mapping this profile to the "
        "PDF congestion signature is our interpretation.",
        "expected": {
            "status": ["diagnosed"],
            "top_cause": "link_congestion",
            "affected_devices": ["SW_CAMPUS_4"],
            "min_evidence_sources": 2,
        },
    },
    "S-03": {
        "title": "Weak Wi-Fi signal (not assessable from the supplied data)",
        "pdf_scenario": "Weak Wi-Fi signal",
        "build": s03,
        "description": "The generator has no wireless signal field. Team-authored records add "
        "an unmapped `wifi_signal_dbm` field and mild loss on SW_CAMPUS_5. NetCoop must not "
        "guess the field's meaning nor claim a weak-signal cause.",
        "expected": {
            "status": ["insufficient_evidence", "diagnosed", "no_fault_detected"],
            "forbidden_causes": ["weak_wifi"],
            "limitations_contain": ["Weak Wi-Fi signal cannot be assessed"],
            "warnings": ["FIELD_UNMAPPED"],
        },
    },
    "S-04": {
        "title": "Ethernet / interface fault",
        "pdf_scenario": "Ethernet or interface fault",
        "build": s04,
        "description": "Generator normal records; SW_CAMPUS_6 mutated with rising interface "
        "errors (40 -> 260) and packet loss, status Warning.",
        "expected": {
            "status": ["diagnosed"],
            "top_cause": "interface_fault",
            "affected_devices": ["SW_CAMPUS_6"],
            "min_evidence_sources": 2,
        },
    },
    "S-05": {
        "title": "DNS failure (team-authored probe data)",
        "pdf_scenario": "DNS or DHCP failure",
        "build": s05,
        "description": "Normal generator telemetry plus TEAM-AUTHORED DNS probe results "
        "(doc 08 §3.3): probes from SW_CAMPUS_4 time out or fail while the network is healthy.",
        "expected": {
            "status": ["diagnosed"],
            "top_cause": "dns_dhcp_failure",
            "affected_devices": ["SW_CAMPUS_4"],
        },
    },
    "S-06": {
        "title": "Interoperability failure (renamed fields, units, minor schema version)",
        "pdf_scenario": "Interoperability failure",
        "build": s06,
        "description": "Generator normal records with team-authored renames: listed aliases "
        "(deviceId, cpu_pct, latency_s in seconds, drops) are mapped and converted; unlisted "
        "names (lat_jitter, link_util) are NOT guessed and become not assessable.",
        "expected": {
            "status": ["no_fault_detected", "insufficient_evidence"],
            "warnings": ["FIELD_ALIAS_APPLIED", "FIELD_UNMAPPED"],
            "forbidden_status": ["diagnosed"],
        },
    },
    "S-06b": {
        "title": "Interoperability failure (unsupported schema major version)",
        "pdf_scenario": "Interoperability failure",
        "build": s06b,
        "description": "Bundle declares schema_version 2.0, for which no adapter exists.",
        "expected": {
            "status": ["failed"],
            "limitations_contain": ["INPUT_SCHEMA_VERSION_UNSUPPORTED"],
        },
    },
    "S-07": {
        "title": "Partially missing metrics",
        "pdf_scenario": None,
        "build": s07,
        "description": "S-02 input with queue_drops removed for SW_CAMPUS_4 and cpu removed "
        "for SW_CAMPUS_8. Missing data must be listed and never treated as healthy.",
        "expected": {
            "status": ["diagnosed", "insufficient_evidence"],
            "forbidden_causes_on_top": ["normal_operation"],
            "warnings": ["METRIC_MISSING"],
            "not_assessable_contains": [
                ["SW_CAMPUS_4", "queue_drops"],
                ["SW_CAMPUS_8", "cpu_utilization_pct"],
            ],
            "confidence_below_scenario": "S-02",
        },
    },
    "S-08": {
        "title": "Insufficient evidence (key evidence removed)",
        "pdf_scenario": None,
        "build": s08,
        "description": "S-02 input with utilization, queue drops, jitter, CPU and status "
        "removed for SW_CAMPUS_4: only latency and loss remain.",
        "expected": {"status": ["insufficient_evidence"], "root_cause_prefix": "Undetermined"},
    },
    "S-09": {
        "title": "Ambiguous: two near-equal explanations",
        "pdf_scenario": None,
        "build": s09,
        "description": "Interface-fault signature on SW_CAMPUS_4 and CPU-overload signature "
        "on SW_CAMPUS_6 with near-equal scores.",
        "expected": {
            "status": ["insufficient_evidence"],
            "clarifications_min": 1,
            "root_cause_prefix": "Undetermined",
        },
    },
    "S-10": {
        "title": "Specialist agent failure (fault injection)",
        "pdf_scenario": None,
        "build": s10,
        "run": {"fault_injection": {"performance_agent": "error"}},
        "description": "S-02 input; performance_agent is made to fail (injected). The run "
        "must degrade, not crash.",
        "expected": {
            "status": ["diagnosed", "insufficient_evidence"],
            "limitations_contain": ["performance_agent"],
            "missing_agents": ["performance_agent"],
        },
    },
    "S-11": {
        "title": "Topology missing",
        "pdf_scenario": None,
        "build": s11,
        "description": "S-02 input without a topology reference.",
        "expected": {
            "status": ["diagnosed", "insufficient_evidence"],
            "limitations_contain": ["No topology available"],
        },
    },
    "S-12": {
        "title": "Conflicting and stale measurements",
        "pdf_scenario": None,
        "build": s12,
        "description": "Two different latency values for SW_CAMPUS_3 at the same timestamp; "
        "SW_CAMPUS_9 reports only data two hours older than the rest.",
        "expected": {
            "status": ["insufficient_evidence"],
            "warnings": ["RECORD_CONFLICT", "DATA_STALE"],
            "limitations_contain": ["SW_CAMPUS_3 latency_ms: observations disagree"],
            "conflicts_min": 1,
        },
    },
}


def build_input(scenario_id: str) -> dict[str, Any]:
    builder: Callable[[], dict[str, Any]] = SCENARIOS[scenario_id]["build"]
    return builder()


def metadata(scenario_id: str) -> dict[str, Any]:
    s = SCENARIOS[scenario_id]
    data = build_input(scenario_id)
    return {
        "id": scenario_id,
        "title": s["title"],
        "pdf_suggested_scenario": s["pdf_scenario"],
        "provenance": data["provenance"],
        "description": s["description"],
        "generator": {
            "notebook_sha256": "f245012f96a878a10653d14df95bdb45cbd6c59f42c8fe61d33efebf70aea460",
            "start": T0.isoformat(),
            "devices": len(DEVICES),
            "samples_per_device": SAMPLES,
        },
        "run": s.get("run", {}),
        "ground_truth": "by construction (doc 09 §3); generator labels only its fault_type",
        "expected": s["expected"],
    }


def dumps(obj: Any) -> str:
    return json.dumps(obj, indent=2, sort_keys=False) + "\n"

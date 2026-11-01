"""Report validation rules (doc 07 §8). Returns a list of violations; empty = valid."""

from __future__ import annotations

import json
from typing import Any

from pydantic import ValidationError

from netcoop.report.builder import OFFICIAL_KEYS
from netcoop.report.official import OfficialReport

STATUSES = {"diagnosed", "insufficient_evidence", "no_fault_detected", "failed"}
EXTENSION_KEY = "netcoop_extensions"


def _str_list(v: Any) -> bool:
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def validate_report(
    report: dict[str, Any],
    *,
    observation_ids: set[str],
    finding_agents: set[str],
    strict: bool = False,
) -> list[str]:
    errors: list[str] = []
    for key in OFFICIAL_KEYS:
        if key not in report:
            errors.append(f"missing official key: {key}")
    allowed = set(OFFICIAL_KEYS) | (set() if strict else {EXTENSION_KEY})
    for key in report:
        if key not in allowed:
            errors.append(f"unexpected top-level key: {key}")
    if errors and any(e.startswith("missing") for e in errors):
        return errors

    if not isinstance(report["incident_id"], str) or not report["incident_id"]:
        errors.append("incident_id must be a non-empty string")
    if report["status"] not in STATUSES:
        errors.append(f"status {report['status']!r} not in {sorted(STATUSES)}")
    if not isinstance(report["suspected_root_cause"], str):
        errors.append("suspected_root_cause must be a string")
    conf = report["confidence"]
    if isinstance(conf, bool) or not isinstance(conf, int | float) or not 0 <= conf <= 1:
        errors.append("confidence must be a number in [0, 1]")
    for key in (
        "affected_devices",
        "alternative_causes",
        "recommended_actions",
        "evidence_sources",
        "limitations",
    ):
        if not _str_list(report[key]):
            errors.append(f"{key} must be a list of strings")
    ev = report["supporting_evidence"]
    if not isinstance(ev, list):
        errors.append("supporting_evidence must be a list")
    else:
        for i, e in enumerate(ev):
            if not isinstance(e, dict) or set(e) != {"metric", "value", "interpretation"}:
                errors.append(
                    f"supporting_evidence[{i}] must have exactly metric/value/interpretation"
                )
                continue
            if isinstance(e["value"], bool) or not isinstance(e["value"], int | float | str):
                errors.append(f"supporting_evidence[{i}].value must be a number or string")

    # Structure and types from the strict ten-key model (doc 07 §1); messages already
    # reported above are not repeated.
    try:
        OfficialReport.model_validate({k: report[k] for k in OFFICIAL_KEYS})
    except ValidationError as exc:
        for err in exc.errors():
            key = str(err["loc"][0])
            if not any(key in e for e in errors):
                loc = ".".join(str(x) for x in err["loc"])
                errors.append(f"official report {loc}: {err['msg']}")

    sources = set(report["evidence_sources"]) if _str_list(report["evidence_sources"]) else set()
    if "community_module" in sources:
        errors.append("community_module must never appear in evidence_sources (doc 07 §3)")
    if not sources <= finding_agents:
        errors.append(f"evidence_sources {sorted(sources - finding_agents)} sent no finding")
    if report["status"] == "insufficient_evidence" and not str(
        report["suspected_root_cause"]
    ).startswith("Undetermined"):
        errors.append("insufficient_evidence must not assert a single cause")
    if report["status"] == "failed" and conf != 0:
        errors.append("failed reports must have confidence 0")
    ext = report.get(EXTENSION_KEY)
    if isinstance(ext, dict):
        for t in ext.get("evidence_trace", []):
            if t.get("observation_id") not in observation_ids:
                errors.append(f"evidence trace {t.get('observation_id')} not in the message log")
        if ext.get("confidence_method") != "heuristic":
            errors.append("confidence_method must stay 'heuristic' until doc 08 §9 is met")
    if "calibrated" in json.dumps(report).lower():
        errors.append("the word 'calibrated' is not allowed before the doc 08 §9 gate is met")
    return errors

"""Unified diagnostic report (doc 07): the ten official keys + one extension block.

The official keys and their order follow ``SRC-1 p5 §6`` exactly. Extended output adds a
single top-level key, ``netcoop_extensions``; :func:`strict_official` drops it.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from netcoop.core.blocks import Observation, ScoredHypothesis
from netcoop.core.messages import Decision, Finding
from netcoop.diagnosis.catalog import CATALOG

OFFICIAL_KEYS: tuple[str, ...] = (
    "incident_id",
    "status",
    "suspected_root_cause",
    "confidence",
    "affected_devices",
    "supporting_evidence",
    "alternative_causes",
    "recommended_actions",
    "evidence_sources",
    "limitations",
)
REPORT_SCHEMA_VERSION = "1.0"
MAX_EVIDENCE = 8
MAX_ALTERNATIVES = 3
#: Same value as the diagnosis gate threshold tau_diag (config/diagnosis.toml).
SEPARATE_ISSUE_MIN = 0.55

HEURISTIC_NOTE = (
    "Confidence is a heuristic score from a documented method (doc 08), not a probability."
)
SIMULATION_NOTE = (
    "Simulation mode: synthetic telemetry and a SIMULATED topology; NetCoop AI has no access "
    "to a real campus network."
)
COUNTER_NOTE = (
    "Whether queue_drops / interface_errors are per-sample or cumulative counters is unknown "
    "in the supplied generator; values are read as reported per sample."
)
_SEV_ORDER = {"critical": 0, "elevated": 1, "normal": 2, "unknown": 3}
_CLASS_ORDER = {"key": 0, "supporting": 1, "weak": 2}


def strict_official(report: dict[str, Any]) -> dict[str, Any]:
    """Exactly the ten official keys, in official order."""
    return {k: report[k] for k in OFFICIAL_KEYS}


def _value(v: float | int | str | None) -> float | int | str:
    if v is None:
        return "unknown"
    if isinstance(v, float):
        return int(v) if v.is_integer() else round(v, 2)
    return v


def _pattern(o: Observation) -> str | None:
    for f in o.quality_flags:
        if f.startswith("pattern:") and f != "pattern:single-sample":
            return f.split(":", 1)[1]
    return None


def interpret(o: Observation) -> str:
    if o.metric.startswith("probe_"):
        return f"Team-authored {o.metric[6:].upper()} service probe from {o.entity}: {o.value}"
    level = {"critical": "Critical", "elevated": "Elevated", "normal": "Normal"}.get(
        o.severity, "Unknown"
    )
    text = f"{level} {o.metric_category.lower()} on {o.entity}"
    pattern = _pattern(o)
    if pattern:
        text += f" ({pattern})"
    if o.assessability == "assessed_with_caveat":
        text += " [stale data]"
    return text


def _observations(findings: dict[str, Finding]) -> dict[str, Observation]:
    return {o.observation_id: o for f in findings.values() for o in f.observations}


def _top(decision: Decision) -> ScoredHypothesis:
    return next(h for h in decision.ranked if h.diagnosable)


def _evidence(decision: Decision, obs: dict[str, Observation]) -> list[Observation]:
    top = _top(decision)
    if decision.decision == "no_fault_detected":
        # One representative per metric: the highest assessed-normal value across devices.
        best: dict[str, Observation] = {}
        for o in obs.values():
            if o.severity != "normal" or o.metric.startswith("probe_"):
                continue
            cur = best.get(o.metric)
            if cur is None or (
                isinstance(o.value, int | float)
                and isinstance(cur.value, int | float)
                and o.value > cur.value
            ):
                best[o.metric] = o
        return [best[m] for m in sorted(best)][:MAX_EVIDENCE]
    spec = CATALOG[top.cause_type]
    cls = {s.item: _CLASS_ORDER[s.cls] for s in spec.signature}
    chosen = [obs[i] for i in top.supporting_observation_ids if i in obs]
    chosen = [o for o in chosen if o.severity != "unknown"]
    chosen.sort(
        key=lambda o: (
            cls.get(o.metric, 1 if o.metric.startswith("probe_") else 3),
            _SEV_ORDER[o.severity],
            o.entity,
            o.metric,
        )
    )
    seen: set[tuple[str, str]] = set()
    out: list[Observation] = []
    for o in chosen:
        if (o.entity, o.metric) in seen:
            continue
        seen.add((o.entity, o.metric))
        out.append(o)
    return out[:MAX_EVIDENCE]


def _label(h: ScoredHypothesis) -> str:
    spec = CATALOG[h.cause_type]
    where = f" on {', '.join(h.entities)}" if h.entities else ""
    return f"{spec.alternative_wording or spec.label}{where} (heuristic score {h.score:.2f})"


def _root_cause(decision: Decision, coverage: float) -> str:
    top = _top(decision)
    spec = CATALOG[top.cause_type]
    if decision.decision == "diagnosed":
        where = f" on {', '.join(top.entities)}" if top.entities else ""
        return f"Likely {spec.label.lower()}{where}"
    if decision.decision == "no_fault_detected":
        return (
            "No fault detected: all assessed measurements are within expected ranges "
            f"({coverage:.0%} of device-metric pairs assessed)"
        )
    candidates = [h for h in decision.ranked if h.diagnosable and h.score > 0][:2]
    names = "; ".join(_label(h) for h in candidates) or "none with supporting evidence"
    return f"Undetermined - leading candidates: {names}"


def _actions(decision: Decision, not_assessable: list[dict[str, str]]) -> tuple[str, list[str]]:
    top = _top(decision)
    if decision.decision == "diagnosed":
        devices = f" ({', '.join(top.entities)})" if top.entities else ""
        return "corrective", [f"{a}{devices}" for a in CATALOG[top.cause_type].actions]
    if decision.decision == "no_fault_detected":
        missing = sorted({n["metric"] for n in not_assessable})
        steps = list(CATALOG["normal_operation"].actions)
        if missing:
            steps.append(
                "Collect the metrics that could not be assessed before concluding full health: "
                + ", ".join(missing)
            )
        return "monitoring", steps
    todo: list[str] = []
    for h in [h for h in decision.ranked if h.diagnosable and h.score > 0][:2]:
        for s in CATALOG[h.cause_type].next_steps:
            line = f"{s} ({', '.join(h.entities)})" if h.entities else s
            if line not in todo:
                todo.append(line)
    if top.missing_expected_evidence:
        todo.append(
            "Collect missing expected evidence: " + ", ".join(top.missing_expected_evidence[:4])
        )
    if not todo:
        todo.append("Collect additional telemetry for the affected scope and re-run diagnosis")
    return "diagnostic_next_todo", todo


def build_report(
    incident_id: str,
    decision: Decision,
    findings: dict[str, Finding],
    *,
    data_quality: dict[str, Any],
    provenance: str,
    mode: str,
    missing_agents: list[str] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    obs = _observations(findings)
    evidence = _evidence(decision, obs)
    not_assessable = sorted(
        {
            (n.entity, n.metric, n.reason, n.detail)
            for f in findings.values()
            for n in f.not_assessable
        }
    )
    na = [{"entity": e, "metric": m, "reason": r, "detail": d} for e, m, r, d in not_assessable]
    coverage = 1.0 - (
        len([n for n in na if n["metric"] != "topology"])
        / max(1, sum(len(f.observations) + len(f.not_assessable) for f in findings.values()))
    )
    mode_name, actions = _actions(decision, na)
    top = _top(decision)
    if decision.decision == "insufficient_evidence":
        alternatives = [_label(h) for h in decision.ranked if h.diagnosable and h.score > 0]
    else:
        alternatives = [
            _label(h) for h in decision.ranked[1:] if h.diagnosable and h.score > 0 and h.entities
        ]
    limitations = [lim.text for lim in decision.limitations]
    if data_quality.get("acceptance") == "READY_WITH_WARNINGS":
        limitations.append(
            "Input accepted with warnings: " + ", ".join(data_quality.get("warnings", []))
        )
    if decision.decision == "diagnosed":
        limitations.append("Root cause requires further verification by an operator.")
    if decision.decision == "diagnosed":
        reported = set(top.entities)
        for h in decision.ranked[1:]:
            outside = sorted(set(h.entities) - reported)
            if h.diagnosable and outside and h.score >= SEPARATE_ISSUE_MIN:
                reported |= set(outside)
                wording = CATALOG[h.cause_type].alternative_wording
                limitations.append(
                    "Possible separate issue not explained by the probable cause: "
                    f"{wording} on {', '.join(outside)} (heuristic score {h.score:.2f})."
                )
    if any(o.metric in ("queue_drops", "interface_errors") for o in evidence):
        limitations.append(COUNTER_NOTE)
    limitations += [HEURISTIC_NOTE, SIMULATION_NOTE]
    conn = findings.get("connectivity_agent")
    facts = conn.facts if conn else {}
    blast = {
        e: {**facts.get("what_if", {}).get(e, {}), "basis": "structural reach, not measured impact"}
        for e in decision.affected_entities
        if e in facts.get("what_if", {})
    }
    report: dict[str, Any] = {
        "incident_id": incident_id,
        "status": decision.decision,
        "suspected_root_cause": _root_cause(decision, coverage),
        "confidence": float(decision.confidence),
        "affected_devices": list(decision.affected_entities),
        "supporting_evidence": [
            {"metric": o.metric, "value": _value(o.value), "interpretation": interpret(o)}
            for o in evidence
        ],
        "alternative_causes": alternatives[:MAX_ALTERNATIVES],
        "recommended_actions": actions,
        "evidence_sources": sorted({o.agent for o in evidence}),
        "limitations": limitations,
    }
    report["netcoop_extensions"] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "mode": mode,
        "data_provenance": provenance,
        "topology_provenance": facts.get("topology_provenance") or "unavailable",
        "confidence_method": "heuristic",
        "confidence_category": decision.confidence_category,
        "decision_margin": decision.margin,
        "gate_checks": decision.gate_checks,
        "data_quality": data_quality,
        "not_assessable": na,
        "hypotheses": [
            h.model_dump(
                mode="json",
                include={
                    "cause_type",
                    "entities",
                    "score",
                    "base",
                    "support",
                    "contradiction",
                    "unexplained",
                    "corroboration",
                    "community_bonus",
                    "ceiling",
                    "matched_signature_items",
                    "missing_expected_evidence",
                    "diagnosable",
                },
            )
            for h in decision.ranked
        ],
        "evidence_trace": [
            {
                "metric": o.metric,
                "entity": o.entity,
                "observation_id": o.observation_id,
                "agent": o.agent,
                "source_ref": o.source_ref,
            }
            for o in evidence
        ],
        "agent_contributions": {
            **{
                a: {
                    "status": "ok",
                    "observations": len(f.observations),
                    "hypotheses": len(f.hypotheses),
                    "tool_calls": len(f.tool_calls),
                    "assessed_fraction": f.self_assessment.assessed_fraction,
                    "budget_exhausted": f.self_assessment.budget_exhausted,
                }
                for a, f in sorted(findings.items())
            },
            **{a: {"status": "missing"} for a in (missing_agents or [])},
        },
        "clarifications": [c.model_dump(mode="json") for c in decision.clarifications],
        "conflicts": [c.model_dump(mode="json") for c in decision.conflicts],
        "blast_radius": blast,
        "recommendation_mode": mode_name,
        "recommendation_status": [
            {
                "action": a,
                "requires_human_approval": True,
                "approval_state": "pending",
                "simulated": True,
            }
            for a in actions
        ],
        "community_signals": [],
        "llm_assistance": [],
        "top_cause_type": top.cause_type,
        "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
    }
    return report


def build_failure_report(
    incident_id: str,
    errors: list[str],
    *,
    mode: str,
    provenance: str,
    data_quality: dict[str, Any] | None = None,
    generated_at: datetime | None = None,
) -> dict[str, Any]:
    """Schema-valid report for rejected input or an internal failure (doc 07 §6)."""
    reason = errors[0] if errors else "unknown error"
    return {
        "incident_id": incident_id,
        "status": "failed",
        "suspected_root_cause": f"No diagnosis was possible: {reason}",
        "confidence": 0.0,
        "affected_devices": [],
        "supporting_evidence": [],
        "alternative_causes": [],
        "recommended_actions": [
            "Correct the input or the failing component and re-run the diagnosis"
        ],
        "evidence_sources": [],
        "limitations": [*errors, SIMULATION_NOTE],
        "netcoop_extensions": {
            "schema_version": REPORT_SCHEMA_VERSION,
            "mode": mode,
            "data_provenance": provenance,
            "confidence_method": "heuristic",
            "confidence_category": "insufficient",
            "errors": errors,
            "data_quality": data_quality or {},
            "recommendation_mode": "fix_input",
            "recommendation_status": [],
            "community_signals": [],
            "llm_assistance": [],
            "generated_at": (generated_at or datetime.now(UTC)).isoformat(),
        },
    }

"""Build the conformance examples and manifest (deterministic; ``--check`` for freshness).

    uv run python -m netcoop.conformance.build          # write conformance/examples + manifest
    uv run python -m netcoop.conformance.build --check  # exit 1 if stale

Every value is ILLUSTRATIVE (stated in the manifest, not inside the messages). Field names
come from doc 06 and terms from the vocabularies; no telemetry is invented beyond that. The
expected verdicts below are written by hand: they are the specification the real parser and
guard are checked against, never derived from running them.
"""

from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

from netcoop.conformance.kit import KIT_DIR, MANIFEST_PATH
from netcoop.core.versioning import PAYLOAD_SCHEMA_VERSION, PROTOCOL_VERSION

T0, T1 = "2026-11-01T09:00:00Z", "2026-11-01T09:15:00Z"
INC = "INC-0001"
WINDOW = {"start": T0, "end": T1}
SNAP = "SNAP-0123456789ab"


def mid(n: int, reply: bool = False) -> str:
    return f"{INC}-MSG-{n:06d}" + (".R" if reply else "")


def env(
    message_id: str,
    sender: str,
    recipient: str,
    message_type: str,
    payload: dict[str, Any],
    in_reply_to: str | None = None,
    status: str = "ok",
) -> dict[str, Any]:
    return {
        "protocol_version": PROTOCOL_VERSION,
        "message_id": message_id,
        "incident_id": INC,
        "in_reply_to": in_reply_to,
        "sender": sender,
        "recipient": recipient,
        "message_type": message_type,
        "sent_at": T0,
        "payload_schema_version": PAYLOAD_SCHEMA_VERSION,
        "status": status,
        "snapshot_id": SNAP,
        "mode": "simulation",
        "data_provenance": "synthetic-generator",
        "payload": payload,
    }


# ------------------------------------------------------------------ payloads


def task(kind: str, n: int, inputs: list[str] | None = None) -> dict[str, Any]:
    goals = {"investigate": "assess_performance", "correlate": "correlate", "report": "report"}
    return {
        "goal": goals[kind],
        "scope_entities": ["SW_CAMPUS_1", "SW_CAMPUS_4"],
        "window": WINDOW,
        "tool_budget": 30 if kind == "investigate" else 0,
        "deadline_s": 10,
        "task_id": f"TASK-{n:04d}",
        "task_kind": kind,
        "input_message_ids": inputs or [],
        "incident_context": {"description": "illustrative example", "trigger": "telemetry_bundle"},
    }


def observation(**over: Any) -> dict[str, Any]:
    o = {
        "observation_id": "OBS-PERF-000001-001",
        "entity": "SW_CAMPUS_4",
        "metric": "latency_ms",
        "metric_category": "Latency",
        "value": 180.0,
        "unit": "millisecond",
        "window": WINDOW,
        "severity": "critical",
        "assessability": "assessed",
        "agent": "performance_agent",
        "aggregation": "worst_by_severity",
        "sample_count": 3,
        "source_ref": ["REC-0001"],
    }
    o.update(over)
    return o


STATUS_UNKNOWN = observation(
    observation_id="OBS-PERF-000001-002",
    entity="SW_CAMPUS_1",
    metric="status",
    metric_category="Device status",
    value=None,
    unit="none",
    severity="unknown",
    assessability="not_assessable",
    not_assessable_reason="MISSING",
    aggregation=None,
    sample_count=0,
    source_ref=[],
)


def hypothesis(**over: Any) -> dict[str, Any]:
    h = {
        "hypothesis_id": "HYP-PERF-000001-001",
        "cause_type": "link_congestion",
        "entities": ["SW_CAMPUS_4"],
        "supporting": [
            {
                "evidence_type": "observation",
                "evidence_id": "OBS-PERF-000001-001",
                "stance": "supports",
                "strength": 0.8,
            }
        ],
        "local_score": 0.8,
        "score_method": "agent_local_heuristic",
        "rationale_code": "HIGH_UTILIZATION_WITH_DELAY",
    }
    h.update(over)
    return h


def finding(**over: Any) -> dict[str, Any]:
    f = {
        "task_id": "TASK-0001",
        "observations": [observation(), STATUS_UNKNOWN],
        "hypotheses": [hypothesis()],
        "not_assessable": [
            {
                "entity": "SW_CAMPUS_1",
                "metric": "status",
                "reason": "MISSING",
                "detail": "no status in the window",
            }
        ],
        "limitations": [],
        "tool_calls": [
            {
                "tool": "telemetry_query",
                "arguments": {"entities": 2},
                "result_summary": "6 samples",
                "at": T0,
            }
        ],
        "self_assessment": {"assessed_fraction": 0.5, "budget_exhausted": False},
    }
    f.update(over)
    return f


QUESTION = {
    "question_type": "recheck_metric",
    "target": "performance_agent",
    "parameters": {"entity": "SW_CAMPUS_4", "metric": "latency_ms"},
    "reason": "narrow_margin",
    "round": 1,
    "clarification_id": "CLR-0001",
}
RANKED = [
    {
        "cause_type": "link_congestion",
        "entities": ["SW_CAMPUS_4"],
        "score": 0.82,
        "support": 0.9,
        "contradiction": 0.0,
        "corroboration": 1.0,
        "ceiling": 1.0,
        "score_method": "heuristic",
    }
]


def decision(kind: str = "diagnosed", **over: Any) -> dict[str, Any]:
    d: dict[str, Any] = {
        "decision": kind,
        "decision_id": "DEC-0001",
        "ranked": RANKED,
        "margin": 0.3,
        "gate_checks": {"score_at_least_tau": True, "margin_at_least_delta": True},
        "confidence": 0.82,
        "confidence_category": "high",
        "score_method": "heuristic",
        "affected_entities": ["SW_CAMPUS_4"],
        "abstention": None,
    }
    if kind == "insufficient_evidence":
        d |= {
            "gate_checks": {"score_at_least_tau": False, "margin_at_least_delta": False},
            "confidence": 0.3,
            "confidence_category": "insufficient",
            "affected_entities": [],
            "abstention": {
                "reasons": ["below_score_threshold", "ambiguous_margin"],
                "evidence_that_would_change_decision": [
                    "evidence that separates the two leading causes"
                ],
            },
        }
    d.update(over)
    return d


REPORT: dict[str, Any] = {
    "incident_id": INC,
    "status": "diagnosed",
    "suspected_root_cause": "Likely link congestion on SW_CAMPUS_4",
    "confidence": 0.82,
    "affected_devices": ["SW_CAMPUS_4"],
    "supporting_evidence": [
        {"metric": "latency_ms", "value": 180.0, "interpretation": "Elevated network latency"}
    ],
    "alternative_causes": ["Upstream link congestion"],
    "recommended_actions": ["Inspect egress link utilization on SW_CAMPUS_4"],
    "evidence_sources": ["performance_agent"],
    "limitations": ["Simulated data; root cause requires further verification"],
}
RECOMMENDATION: dict[str, Any] = {
    "recommendation_id": "RCM-0001",
    "action_text": REPORT["recommended_actions"][0],
    "kind": "corrective",
    "target_entities": ["SW_CAMPUS_4"],
    "reason": REPORT["suspected_root_cause"],
    "priority": "high",
    "precautions": ["Simulated only: nothing is executed on a network."],
    "requires_human_approval": True,
    "simulated": True,
    "verification_step": "Re-run the diagnosis on fresh simulated data",
}
AGENT_ERROR = {
    "code": "AGENT_TIMEOUT",
    "message": "no reply within 10s",
    "recoverable": True,
    "related_message_id": mid(1),
    "details": {"deadline_s": 10},
}
CANDIDATE = {
    "candidate_id": "CAND-0001",
    "zone": "ZONE_HOSTEL_A",
    "symptom_categories": ["disconnects"],
    "window": WINDOW,
    "complaint_count": 3,
    "distinct_reporters": 3,
    "trust_label": "reported_unverified",
    "complaint_ids": ["CMP-0001", "CMP-0002", "CMP-0003"],
}

# ------------------------------------------------------------------ valid single messages

VALID: dict[str, tuple[str, dict[str, Any]]] = {
    "task_request_investigate": (
        "An investigate task for a specialist",
        env(mid(1), "orchestrator", "performance_agent", "task_request", task("investigate", 1)),
    ),
    "task_request_correlate": (
        "A correlate task that points at findings by id (references)",
        env(
            mid(4),
            "orchestrator",
            "correlation_agent",
            "task_request",
            task("correlate", 4, [mid(1, True), mid(2, True), mid(3, True)]),
        ),
    ),
    "finding_with_not_assessable": (
        "A finding with an assessed observation, a status-unknown "
        "observation (not assessable, no value) and a hypothesis citing evidence",
        env(mid(1, True), "performance_agent", "orchestrator", "finding", finding(), mid(1)),
    ),
    "clarification_request": (
        "The correlation agent asks a question",
        env(
            mid(4, True),
            "correlation_agent",
            "orchestrator",
            "clarification_request",
            QUESTION,
            mid(4),
        ),
    ),
    "clarification_response_answered": (
        "A clarification answered with a new observation",
        env(
            mid(5, True),
            "performance_agent",
            "orchestrator",
            "clarification_response",
            {
                "answered": True,
                "answerable": "yes",
                "clarification_id": "CLR-0001",
                "source": "performance_agent",
                "observations": [observation(observation_id="OBS-PERF-000005-001")],
            },
            mid(5),
        ),
    ),
    "clarification_response_unanswered": (
        "A clarification the target cannot answer",
        env(
            mid(5, True),
            "performance_agent",
            "orchestrator",
            "clarification_response",
            {
                "answered": False,
                "answerable": "no",
                "clarification_id": "CLR-0001",
                "source": "performance_agent",
                "reason": "no data for the entity",
            },
            mid(5),
        ),
    ),
    "decision_diagnosed": (
        "A diagnosed decision (heuristic score, no abstention block)",
        env(mid(6, True), "correlation_agent", "orchestrator", "decision", decision(), mid(6)),
    ),
    "decision_with_abstention": (
        "An insufficient_evidence decision explaining why it abstains",
        env(
            mid(6, True),
            "correlation_agent",
            "orchestrator",
            "decision",
            decision("insufficient_evidence"),
            mid(6),
        ),
    ),
    "report_ready_with_recommendation": (
        "The ten-key report plus a structured recommendation "
        "(always simulated, always needs approval)",
        env(
            mid(7, True),
            "reporting_agent",
            "orchestrator",
            "report_ready",
            {"report": REPORT, "recommendations": [RECOMMENDATION]},
            mid(7),
        ),
    ),
    "agent_error": (
        "The orchestrator records a timeout against the task it concerns",
        env(
            mid(8), "orchestrator", "performance_agent", "agent_error", AGENT_ERROR, mid(1), "error"
        ),
    ),
    "community_candidate": (
        "Extension A: a community candidate (reported, unverified)",
        env(mid(9), "community_module", "orchestrator", "community_candidate", CANDIDATE),
    ),
    "protocol_1_0_message": (
        "A protocol 1.0 message (no snapshot/mode/provenance/seq) still parses",
        {
            k: v
            for k, v in env(
                mid(1), "orchestrator", "performance_agent", "task_request", task("investigate", 1)
            ).items()
            if k not in ("snapshot_id", "mode", "data_provenance")
        }
        | {"protocol_version": "1.0"},
    ),
}


# ------------------------------------------------------------------ invalid single messages


def mutate(name: str, fn: Any) -> dict[str, Any]:
    msg = copy.deepcopy(VALID[name][1])
    fn(msg)
    return msg


def _drop(key: str) -> Any:
    return lambda m: m.pop(key)


INVALID: dict[str, tuple[str, str, dict[str, Any], int | None]] = {
    "missing_required_field": (
        "message_id is missing",
        "MESSAGE_INVALID",
        mutate("task_request_investigate", _drop("message_id")),
        None,
    ),
    "wrong_type": (
        "tool_budget is a string, not a number",
        "MESSAGE_INVALID",
        mutate(
            "task_request_investigate", lambda m: m["payload"].__setitem__("tool_budget", "many")
        ),
        None,
    ),
    "unknown_vocabulary_term": (
        "cause_type is not a registered term",
        "UNKNOWN_TERM",
        mutate(
            "finding_with_not_assessable",
            lambda m: m["payload"]["hypotheses"][0].__setitem__("cause_type", "alien_attack"),
        ),
        None,
    ),
    "unit_not_matching_metric": (
        "latency_ms declared in percent",
        "UNIT_INCOMPATIBLE",
        mutate(
            "finding_with_not_assessable",
            lambda m: m["payload"]["observations"][0].__setitem__("unit", "percent"),
        ),
        None,
    ),
    "not_assessable_with_value": (
        "a not_assessable observation carries a value",
        "ASSESSABILITY_VALUE_MISMATCH",
        mutate(
            "finding_with_not_assessable",
            lambda m: m["payload"]["observations"][1].__setitem__("value", "up"),
        ),
        None,
    ),
    "mode_deployment": (
        "mode is 'deployment' (only simulation exists)",
        "MODE_NOT_ALLOWED",
        mutate("task_request_investigate", lambda m: m.__setitem__("mode", "deployment")),
        None,
    ),
    "naive_timestamp": (
        "sent_at has no timezone",
        "MESSAGE_INVALID",
        mutate(
            "task_request_investigate", lambda m: m.__setitem__("sent_at", "2026-11-01T09:00:00")
        ),
        None,
    ),
    "unsupported_major_version": (
        "protocol_version 2.0",
        "PROTOCOL_VERSION_UNSUPPORTED",
        mutate("task_request_investigate", lambda m: m.__setitem__("protocol_version", "2.0")),
        None,
    ),
    "hypothesis_without_evidence": (
        "a hypothesis cites nothing and names nothing missing",
        "HYPOTHESIS_WITHOUT_EVIDENCE",
        mutate(
            "finding_with_not_assessable",
            lambda m: m["payload"]["hypotheses"][0].__setitem__("supporting", []),
        ),
        None,
    ),
    "evidence_wrong_prefix": (
        "an observation reference with a HYP- id",
        "EVIDENCE_PREFIX_MISMATCH",
        mutate(
            "finding_with_not_assessable",
            lambda m: m["payload"]["hypotheses"][0]["supporting"][0].__setitem__(
                "evidence_id", "HYP-PERF-000001-001"
            ),
        ),
        None,
    ),
    "oversize_message": (
        "larger than the size limit (checked with max_bytes=2048)",
        "MESSAGE_TOO_LARGE",
        mutate(
            "task_request_investigate",
            lambda m: m["payload"]["incident_context"].__setitem__("description", "x" * 3000),
        ),
        2048,
    ),
    "calibrated_score_method": (
        "score_method 'calibrated' is a blocked term",
        "UNKNOWN_TERM",
        mutate(
            "decision_diagnosed", lambda m: m["payload"].__setitem__("score_method", "calibrated")
        ),
        None,
    ),
    "recommendation_not_simulated": (
        "a recommendation sets simulated to false",
        "RECOMMENDATION_SAFETY_VIOLATION",
        mutate(
            "report_ready_with_recommendation",
            lambda m: m["payload"]["recommendations"][0].__setitem__("simulated", False),
        ),
        None,
    ),
    "abstention_missing": (
        "insufficient_evidence with abstention null",
        "ABSTENTION_MISMATCH",
        mutate("decision_with_abstention", lambda m: m["payload"].__setitem__("abstention", None)),
        None,
    ),
}


# ------------------------------------------------------------------ conversations


def step(state: str, msg: dict[str, Any]) -> dict[str, Any]:
    return {"incident_state": state, "message": msg}


def happy() -> list[dict[str, Any]]:
    q2 = QUESTION | {"round": 2, "clarification_id": "CLR-0002"}
    return [
        step(
            "READY",
            env(
                mid(1), "orchestrator", "performance_agent", "task_request", task("investigate", 1)
            ),
        ),
        step(
            "COLLECTING",
            env(mid(1, True), "performance_agent", "orchestrator", "finding", finding(), mid(1)),
        ),
        step(
            "CORRELATING",
            env(
                mid(2),
                "orchestrator",
                "correlation_agent",
                "task_request",
                task("correlate", 2, [mid(1, True)]),
            ),
        ),
        step(
            "CORRELATING",
            env(
                mid(2, True),
                "correlation_agent",
                "orchestrator",
                "clarification_request",
                QUESTION,
                mid(2),
            ),
        ),
        step(
            "CLARIFYING",
            env(
                mid(3),
                "orchestrator",
                "performance_agent",
                "clarification_request",
                QUESTION,
                mid(2, True),
            ),
        ),
        step(
            "CLARIFYING",
            env(
                mid(3, True),
                "performance_agent",
                "orchestrator",
                "clarification_response",
                {
                    "answered": False,
                    "answerable": "no",
                    "clarification_id": "CLR-0001",
                    "reason": "no new data",
                },
                mid(3),
            ),
        ),
        step(
            "CORRELATING",
            env(
                mid(4),
                "orchestrator",
                "correlation_agent",
                "task_request",
                task("correlate", 3, [mid(1, True)]),
            ),
        ),
        step(
            "CORRELATING",
            env(
                mid(4, True),
                "correlation_agent",
                "orchestrator",
                "clarification_request",
                q2,
                mid(4),
            ),
        ),
        step(
            "CLARIFYING",
            env(
                mid(5),
                "orchestrator",
                "performance_agent",
                "clarification_request",
                q2,
                mid(4, True),
            ),
        ),
        step(
            "CLARIFYING",
            env(
                mid(5, True),
                "performance_agent",
                "orchestrator",
                "clarification_response",
                {
                    "answered": False,
                    "answerable": "no",
                    "clarification_id": "CLR-0002",
                    "reason": "no new data",
                },
                mid(5),
            ),
        ),
        step(
            "CORRELATING",
            env(
                mid(6),
                "orchestrator",
                "correlation_agent",
                "task_request",
                task("correlate", 4, [mid(1, True)]),
            ),
        ),
        step(
            "CORRELATING",
            env(mid(6, True), "correlation_agent", "orchestrator", "decision", decision(), mid(6)),
        ),
        step(
            "REPORTING",
            env(
                mid(7),
                "orchestrator",
                "reporting_agent",
                "task_request",
                task("report", 5, [mid(1, True), mid(6, True)]),
            ),
        ),
        step(
            "REPORTING",
            env(
                mid(7, True),
                "reporting_agent",
                "orchestrator",
                "report_ready",
                {"report": REPORT, "recommendations": [RECOMMENDATION]},
                mid(7),
            ),
        ),
    ]


H = happy()
Q3 = QUESTION | {"round": 3, "clarification_id": "CLR-0003"}
CONVERSATIONS: dict[str, tuple[str, str | None, list[dict[str, Any]], int | None]] = {
    "valid_full_incident": (
        "A complete legal incident: task, finding, two clarification rounds, decision, report",
        None,
        H,
        None,
    ),
    "performance_agent_sends_decision": (
        "performance_agent tries to send the decision",
        "SENDER_NOT_AUTHORIZED",
        [
            *H[:3],
            step(
                "CORRELATING",
                env(
                    mid(2, True),
                    "performance_agent",
                    "orchestrator",
                    "decision",
                    decision(),
                    mid(1),
                ),
            ),
        ],
        3,
    ),
    "finding_replies_to_nothing": (
        "a finding that answers a task that does not exist",
        "REPLY_MISMATCH",
        [
            H[0],
            step(
                "COLLECTING",
                env(
                    mid(1, True), "performance_agent", "orchestrator", "finding", finding(), mid(99)
                ),
            ),
        ],
        1,
    ),
    "third_clarification_round": (
        "a third question when the limit is two rounds",
        "CLARIFICATION_LIMIT_EXCEEDED",
        [
            *H[:11],
            step(
                "CORRELATING",
                env(
                    mid(6, True),
                    "correlation_agent",
                    "orchestrator",
                    "clarification_request",
                    Q3,
                    mid(6),
                ),
            ),
        ],
        11,
    ),
    "direct_agent_to_agent": (
        "performance_agent sends its finding straight to the correlation agent",
        "DIRECT_AGENT_MESSAGE_FORBIDDEN",
        [
            H[0],
            step(
                "COLLECTING",
                env(
                    mid(1, True),
                    "performance_agent",
                    "correlation_agent",
                    "finding",
                    finding(),
                    mid(1),
                ),
            ),
        ],
        1,
    ),
    "message_after_incident_closed": (
        "an agent error after the incident is complete",
        "INCIDENT_CLOSED",
        [
            *H,
            step(
                "COMPLETE",
                env(
                    mid(8),
                    "orchestrator",
                    "reporting_agent",
                    "agent_error",
                    AGENT_ERROR,
                    mid(7, True),
                    "error",
                ),
            ),
        ],
        len(H),
    ),
    "community_with_extension_off": (
        "a community candidate while community_signals is off",
        "EXTENSION_DISABLED",
        [step("READY", VALID["community_candidate"][1])],
        0,
    ),
}


# ------------------------------------------------------------------ write


def _dump(obj: Any) -> str:
    return json.dumps(obj, indent=2, ensure_ascii=False) + "\n"


def build() -> dict[Path, str]:
    files: dict[Path, str] = {}
    examples: list[dict[str, Any]] = []
    for name, (desc, msg) in VALID.items():
        rel = f"examples/valid/{name}.json"
        files[KIT_DIR / rel] = _dump(msg)
        examples.append(
            {
                "path": rel,
                "kind": "message",
                "description": desc,
                "expected_verdict": "accepted",
                "expected_code": None,
            }
        )
    for name, (desc, code, msg, max_bytes) in INVALID.items():
        rel = f"examples/invalid/{name}.json"
        files[KIT_DIR / rel] = _dump(msg)
        entry: dict[str, Any] = {
            "path": rel,
            "kind": "message",
            "description": desc,
            "expected_verdict": "rejected",
            "expected_code": code,
        }
        if max_bytes:
            entry["max_bytes"] = max_bytes
        examples.append(entry)
    for name, (desc, conv_code, steps, index) in CONVERSATIONS.items():
        rel = f"examples/conversations/{name}.json"
        files[KIT_DIR / rel] = _dump(
            {"description": desc, "max_clarification_rounds": 2, "extensions": [], "steps": steps}
        )
        examples.append(
            {
                "path": rel,
                "kind": "conversation",
                "description": desc,
                "expected_verdict": "rejected" if conv_code else "accepted",
                "expected_code": conv_code,
                "failing_index": index,
            }
        )
    files[MANIFEST_PATH] = _dump(
        {
            "protocol_version": PROTOCOL_VERSION,
            "note": "All values are ILLUSTRATIVE (simulated); they are not measurements of any "
            "real network. Field names follow doc 06, terms the vocabularies.",
            "examples": examples,
        }
    )
    return files


def main(argv: list[str]) -> int:
    check = "--check" in argv
    stale = []
    for path, content in build().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            stale.append(path)
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    if check and stale:
        print(
            "stale conformance files (run python -m netcoop.conformance.build):", *stale, sep="\n  "
        )
        return 1
    print("up to date" if not stale else f"wrote {len(stale)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

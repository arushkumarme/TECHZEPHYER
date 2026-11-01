"""Closed vocabularies of the NetCoop protocol (doc 05 §2-§4, doc 03 §3, doc 08 §3.1).

Closed lists are enforced on every message hop; a value outside a list makes the
message invalid (doc 05 principle 4).
"""

from __future__ import annotations

from typing import Literal, get_args

AgentId = Literal[
    "orchestrator",
    "performance_agent",
    "infrastructure_agent",
    "connectivity_agent",
    "correlation_agent",
    "reporting_agent",
    "community_module",
]

SPECIALIST_AGENTS: tuple[AgentId, ...] = (
    "performance_agent",
    "infrastructure_agent",
    "connectivity_agent",
)

MessageType = Literal[
    "task_request",
    "finding",
    "clarification_request",
    "clarification_response",
    "decision",
    "report_ready",
    "agent_error",
    "community_candidate",
    "conflict_report",
    "conflict_response",
]

#: Message types that answer an earlier message and therefore need ``in_reply_to``.
RESPONSE_TYPES: frozenset[str] = frozenset(
    {"finding", "clarification_response", "decision", "report_ready", "conflict_response"}
)

MessageStatus = Literal["ok", "partial", "error"]

#: Hypothesis catalog cause types (doc 08 §3.1).
CauseType = Literal[
    "normal_operation",
    "link_congestion",
    "upstream_congestion",
    "weak_wifi",
    "interface_fault",
    "device_overload",
    "device_failure",
    "dns_dhcp_failure",
    "telemetry_unreliable",
]
CAUSE_TYPES: tuple[str, ...] = get_args(CauseType)

Severity = Literal["normal", "elevated", "critical", "unknown"]
Assessability = Literal["assessed", "assessed_with_caveat", "not_assessable"]
NotAssessableReason = Literal[
    "MISSING",
    "MALFORMED",
    "UNMAPPED_FIELD",
    "UNIT_AMBIGUOUS",
    "STALE",
    "INSUFFICIENT_SAMPLES",
    "NO_TOPOLOGY",
    "OUT_OF_SCOPE",
    "IMPLAUSIBLE",
]
#: Evidence classes used by conflict rule 1 (doc 08 §5).
EvidenceClass = Literal["direct_measurement", "derived", "user_report"]

QuestionType = Literal[
    "widen_time_window",
    "assess_additional_entities",
    "what_if_cause",
    "recheck_metric",
]
ClarificationReason = Literal["conflict", "narrow_margin", "missing_expected_evidence"]

DecisionKind = Literal["diagnosed", "insufficient_evidence", "no_fault_detected"]
ConfidenceCategory = Literal["high", "medium", "low", "insufficient"]
TrustLabel = Literal["reported_unverified", "detected", "corroborated"]
ConflictRule = Literal["evidence_class", "freshness", "topology_consistency", "unresolved"]

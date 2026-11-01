"""Fault Correlation Agent — ``correlation_agent`` (A-CORR, doc 03 §2.4).

Turns the specialists' independent findings into one ranked set of explanations using the
deterministic diagnosis knowledge (doc 08), or concludes the evidence is insufficient.

Bounded clarification (doc 03 §3): the agent is stateless. Its reply to a ``task_request``
is either a ``decision`` or a ``clarification_request``. The orchestrator routes the
question, then sends a new task whose context carries every question/answer so far and the
round number. A question is asked only for a stated reason (unresolved conflict, narrow
margin), never twice, and never once ``max_rounds`` questions have been asked — then the
agent decides on what it has and records the unanswered need as a limitation.
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from netcoop.config.fields import FieldDictionary, load_field_dictionary
from netcoop.core.blocks import (
    ClarificationRecord,
    ConflictTrailEntry,
    EvidenceRef,
    Limitation,
    NotAssessableItem,
    Observation,
)
from netcoop.core.bus import MessageBus
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    ClarificationResponse,
    ConflictParty,
    ConflictReport,
    ConflictSide,
    Decision,
    Envelope,
    Finding,
    ParsedMessage,
    TaskRequest,
)
from netcoop.core.vocab import SPECIALIST_AGENTS, AgentId
from netcoop.diagnosis.catalog import CATALOG, availability
from netcoop.diagnosis.evidence import EvidenceView, build_view
from netcoop.diagnosis.params import DiagnosisParams
from netcoop.diagnosis.scoring import (
    CommunityContext,
    DiagnosisContext,
    decide,
    score_hypotheses,
)
from netcoop.ingestion.models import NormalizedBundle
from netcoop.ingestion.normalize import parse_timestamp

_DATA_PROBLEMS = {"UNMAPPED_FIELD", "UNIT_AMBIGUOUS", "MALFORMED", "IMPLAUSIBLE"}
_TOPOLOGY_CAUSES = {"device_failure", "upstream_congestion"}


def correlation_context(
    bundle: NormalizedBundle,
    findings: dict[str, Finding],
    *,
    missing_agents: list[str],
    clarifications: list[dict[str, Any]],
    round_no: int,
    max_rounds: int,
    community: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """The JSON context the orchestrator sends with every correlation task."""
    dq = bundle.data_quality
    return {
        "findings": {a: f.model_dump(mode="json") for a, f in sorted(findings.items())},
        "data_quality": {
            "completeness": dq.completeness,
            "freshness": dq.freshness,
            "consistency": dq.consistency,
            "q": dq.q,
            "acceptance": dq.acceptance,
            "warnings": dq.warnings,
        },
        "entities": list(bundle.entities),
        "items_per_entity": list(bundle.assessable_items),
        "probes_present": bool(bundle.probes),
        "missing_agents": sorted(missing_agents),
        "clarifications": clarifications,
        "round": round_no,
        "max_rounds": max_rounds,
        "window": {
            "start": bundle.window.start.isoformat(),
            "end": bundle.window.end.isoformat(),
        },
        "community": community or [],
    }


class CorrelationAgent:
    agent_id: AgentId = "correlation_agent"

    def __init__(
        self, bus: MessageBus, params: DiagnosisParams, fields: FieldDictionary | None = None
    ) -> None:
        self.bus = bus
        self.params = params
        self.fields = fields or load_field_dictionary()

    def handle(self, msg: ParsedMessage) -> Envelope:
        try:
            if not isinstance(msg.payload, TaskRequest):
                raise ValueError(f"correlation_agent cannot handle {msg.envelope.message_type}")
            ctx = msg.payload.context
            reply = self.correlate(ctx)
            if isinstance(reply, ClarificationRequest):
                # One question per round, so the round number identifies it.
                reply = reply.model_copy(update={"clarification_id": f"CLR-{reply.round:04d}"})
                report = self.conflict_report(reply, ctx) if reply.reason == "conflict" else None
                if report is not None:  # protocol 1.2: the conflict re-check, as a conflict
                    return self.bus.reply(msg, message_type="conflict_report", payload=report)
                return self.bus.reply(msg, message_type="clarification_request", payload=reply)
            # One decision per incident (doc 04 §5).
            reply = reply.model_copy(
                update={"decision_id": "DEC-0001", "conflict_trail": _trail(reply, ctx)}
            )
            return self.bus.reply(msg, message_type="decision", payload=reply)
        except Exception as exc:
            return self.bus.reply(
                msg,
                message_type="agent_error",
                payload=AgentError(
                    code="AGENT_FAILED", message=f"{type(exc).__name__}: {exc}", recoverable=False
                ),
                status="error",
            )

    # ------------------------------------------------------------------ conflicts (1.2)
    def conflict_report(
        self, question: ClarificationRequest, ctx: dict[str, Any]
    ) -> ConflictReport | None:
        """The existing conflict re-check (doc 08 §5: an unresolved observation conflict),
        stated as a conflict_report: parties, the evidence on each side, the rule. Detection
        and resolution are unchanged; this only makes the disagreement a logged exchange."""
        view, _, _ = self.build(ctx)
        entity, metric = question.parameters.get("entity"), question.parameters.get("metric")
        conflict = next(
            (
                c
                for c in view.conflicts
                if c.rule == "unresolved" and c.description.split(":")[0] == f"{entity} {metric}"
            ),
            None,
        )
        if conflict is None:
            return None
        observations = {
            o.observation_id: o
            for f in ctx["findings"].values()
            for o in Finding.model_validate(f).observations
        }
        involved = [observations[i] for i in conflict.observation_ids if i in observations]
        if len(involved) < 2:
            return None
        hypotheses: dict[str, list[str]] = {}
        for agent, f in ctx["findings"].items():
            for h in Finding.model_validate(f).hypotheses:
                if set(h.supporting_observation_ids) & set(conflict.observation_ids):
                    hypotheses.setdefault(agent, []).append(h.hypothesis_id)
        parties = [
            ConflictParty(
                agent=agent,
                hypothesis_ids=hypotheses.get(agent, []),
                observation_ids=[o.observation_id for o in involved if o.agent == agent],
            )
            for agent in sorted({o.agent for o in involved})
        ]
        sides = [
            ConflictSide(
                agent=o.agent,
                claim=f"{o.entity} {o.metric} = {o.value} {o.unit} ({o.severity})",
                evidence=[
                    EvidenceRef(
                        evidence_type="observation", evidence_id=o.observation_id, stance="supports"
                    )
                ],
            )
            for o in involved
        ]
        return ConflictReport(
            conflict_id=conflict.conflict_id,
            conflict_type="observation_contradiction",
            parties=parties,
            sides=sides,
            reason_code="CONFLICTING_READINGS",
            reason_text=conflict.description,
            proposed_rule=conflict.rule,
            effect_on_confidence="Both readings are kept; the conflict caps confidence until a "
            "re-check settles it (doc 08 §5).",
            target=question.target,
            recheck={"question_type": question.question_type, **question.parameters},
            round=question.round,
            clarification_id=question.clarification_id,
        )

    # ------------------------------------------------------------------ core
    def build(self, ctx: dict[str, Any]) -> tuple[EvidenceView, DiagnosisContext, float]:
        findings = {a: Finding.model_validate(f) for a, f in ctx["findings"].items()}
        observations: list[Observation] = [o for f in findings.values() for o in f.observations]
        not_assessable: list[NotAssessableItem] = [
            n for f in findings.values() for n in f.not_assessable
        ]
        conn = findings.get("connectivity_agent")
        facts: dict[str, Any] = json.loads(json.dumps(conn.facts)) if conn else {}
        facts.setdefault("topology_available", False)
        for c in ctx.get("clarifications", []):
            resp = ClarificationResponse.model_validate(c["response"])
            if not resp.answered:
                continue
            observations.extend(resp.observations)
            if resp.result and "isolated" in resp.result:
                facts.setdefault("what_if", {})[resp.result["entity"]] = {
                    "isolated": resp.result["isolated"],
                    "degraded": resp.result.get("degraded", []),
                }
        view = build_view(
            observations,
            not_assessable,
            facts=facts,
            params=self.params,
            entities=list(ctx["entities"]),
            items_per_entity=list(ctx["items_per_entity"]),
        )
        window = ctx.get("window", {})
        community = [
            CommunityContext(
                candidate_id=c["candidate_id"],
                entities=tuple(c["entities"]),
                start=_required_time(c["start"]),
                end=_required_time(c["end"]),
            )
            for c in ctx.get("community", [])
        ]
        dctx = DiagnosisContext(
            q=float(ctx["data_quality"]["q"]),
            topology_available=bool(facts.get("topology_available")),
            available=availability(self.fields, probes_present=bool(ctx.get("probes_present"))),
            missing_agents=list(ctx.get("missing_agents", [])),
            window_start=parse_timestamp(window.get("start")),
            window_end=parse_timestamp(window.get("end")),
            community=community,
        )
        items = [i for i in view.items_per_entity]
        assessed = sum(1 for (_, i) in view.items if i in items)
        coverage = assessed / max(1, len(view.entities) * len(items))
        return view, dctx, coverage

    def correlate(self, ctx: dict[str, Any]) -> Decision | ClarificationRequest:
        view, dctx, coverage = self.build(ctx)
        problem_agents = {
            a
            for a, f in ctx["findings"].items()
            if any(n["reason"] in _DATA_PROBLEMS for n in f.get("not_assessable", []))
        }
        ranked = score_hypotheses(view, dctx, self.params, problem_agents=problem_agents)
        decision = decide(ranked, view, dctx, self.params, coverage=coverage)
        asked = ctx.get("clarifications", [])
        question = self._question(decision, view, ctx)
        if question is not None and len(asked) < int(ctx.get("max_rounds", 0)):
            return question
        records = [
            ClarificationRecord(
                round=i + 1,
                question_type=c["request"]["question_type"],
                target=c["request"]["target"],
                reason=c["request"]["reason"],
                answered=bool(c["response"].get("answered")),
                summary=_summary(c),
            )
            for i, c in enumerate(asked)
        ]
        limitations = list(decision.limitations)
        if question is not None:
            limitations.append(
                Limitation(
                    code="CLARIFICATION_LIMIT_REACHED",
                    text=f"Clarification limit ({ctx.get('max_rounds', 0)}) reached; unanswered: "
                    f"{question.question_type} to {question.target} ({question.reason}).",
                )
            )
        return decision.model_copy(update={"clarifications": records, "limitations": limitations})

    def _question(
        self, decision: Decision, view: EvidenceView, ctx: dict[str, Any]
    ) -> ClarificationRequest | None:
        if decision.decision != "insufficient_evidence":
            return None
        asked = {
            json.dumps(
                [c["request"]["question_type"], c["request"]["target"], c["request"]["parameters"]],
                sort_keys=True,
            )
            for c in ctx.get("clarifications", [])
        }
        round_no = len(ctx.get("clarifications", [])) + 1
        missing = set(ctx.get("missing_agents", []))
        candidates: list[ClarificationRequest] = []
        for c in view.conflicts:
            if c.rule != "unresolved":
                continue
            entity, metric = c.description.split(":")[0].split(" ")
            target = next(
                (ev.agents[0] for k, ev in view.items.items() if k == (entity, metric)), None
            )
            if target in SPECIALIST_AGENTS and target not in missing:
                candidates.append(
                    ClarificationRequest(
                        question_type="recheck_metric",
                        target=target,
                        parameters={"entity": entity, "metric": metric},
                        reason="conflict",
                        round=round_no,
                    )
                )
        if decision.gate_checks.get("margin_at_least_delta") is False:
            pair = [h for h in decision.ranked if h.diagnosable][:2]
            what_if = view.facts.get("what_if", {})
            for h in pair:
                if (
                    h.cause_type in _TOPOLOGY_CAUSES
                    and view.facts.get("topology_available")
                    and "connectivity_agent" not in missing
                ):
                    for e in h.entities:
                        if e not in what_if:
                            candidates.append(
                                ClarificationRequest(
                                    question_type="what_if_cause",
                                    target="connectivity_agent",
                                    parameters={"entity": e},
                                    reason="narrow_margin",
                                    round=round_no,
                                )
                            )
            for h in pair:
                key = next(
                    (s.item for s in CATALOG[h.cause_type].signature if s.cls == "key"), None
                )
                for e in h.entities:
                    ev = view.get(e, key) if key else None
                    if (
                        ev is not None
                        and ev.agents[0] in SPECIALIST_AGENTS
                        and ev.agents[0] not in missing
                    ):
                        candidates.append(
                            ClarificationRequest(
                                question_type="recheck_metric",
                                target=ev.agents[0],
                                parameters={"entity": e, "metric": key},
                                reason="narrow_margin",
                                round=round_no,
                            )
                        )
        for q in candidates:
            sig = json.dumps([q.question_type, q.target, q.parameters], sort_keys=True)
            if sig not in asked:
                return q
        return None


def _required_time(value: Any) -> datetime:
    t = parse_timestamp(value)
    if t is None:
        raise ValueError(f"community candidate time {value!r} is not an ISO timestamp")
    return t


def _summary(c: dict[str, Any]) -> str:
    resp = c["response"]
    if not resp.get("answered"):
        return f"not answered: {resp.get('reason')}"
    if resp.get("result"):
        r = resp["result"]
        return (
            f"what-if {r.get('entity')}: isolated={r.get('isolated')} degraded={r.get('degraded')}"
        )
    checked = [f"{o['entity']} {o['metric']}={o['severity']}" for o in resp.get("observations", [])]
    return "re-checked " + ", ".join(checked)


def _trail(decision: Decision, ctx: dict[str, Any]) -> list[ConflictTrailEntry]:
    """Every conflict with the rule applied; an unresolved one keeps both sides."""
    raised = {c["request"].get("conflict_id") for c in ctx.get("clarifications", [])} - {None}
    return [
        ConflictTrailEntry(
            conflict_id=c.conflict_id,
            rule=c.rule,
            status="unresolved_preserved" if c.rule == "unresolved" else "resolved",
            raised=c.conflict_id in raised,
            preserved_observation_ids=list(c.observation_ids) if c.rule == "unresolved" else [],
        )
        for c in decision.conflicts
    ]

"""Deterministic orchestrator (doc 04). Ordinary code, not an AI.

One call to :meth:`Orchestrator.run` takes a telemetry bundle from ``RECEIVED`` to a
terminal or review state, logging every transition and every message:

``RECEIVED → VALIDATING → READY[_WITH_WARNINGS] → DISPATCHED → COLLECTING →
CORRELATING (⇄ CLARIFYING) → DECIDED → REPORTING → AWAITING_REVIEW | COMPLETE``,
with ``REJECTED`` and ``FAILED`` exits.

Determinism (doc 04 §4): requests are built in this thread in a fixed agent order, replies
get ids derived from their request, findings are consumed in fixed order, and clarification
rounds are sequential. Parallel and sequential runs therefore log the same messages.
"""

from __future__ import annotations

import concurrent.futures as cf
from dataclasses import dataclass, field
from typing import Any

from netcoop.agents.connectivity import ConnectivityAgent
from netcoop.agents.correlation import CorrelationAgent, correlation_context
from netcoop.agents.infrastructure import InfrastructureAgent
from netcoop.agents.performance import PerformanceAgent
from netcoop.agents.reporting import ReportingAgent, reporting_context
from netcoop.config.settings import Settings, load_settings
from netcoop.core.blocks import TimeWindow
from netcoop.core.bus import Handler, MessageBus
from netcoop.core.ids import Clock, IdFactory, SystemClock
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    Decision,
    Finding,
    MessageValidationError,
    ParsedMessage,
    ReportReady,
    TaskRequest,
)
from netcoop.core.vocab import SPECIALIST_AGENTS, AgentId
from netcoop.diagnosis.params import DiagnosisParams, load_diagnosis_params
from netcoop.ingestion.issues import IngestIssue
from netcoop.ingestion.models import NormalizedBundle
from netcoop.ingestion.normalize import ingest
from netcoop.orchestrator.faults import inject
from netcoop.orchestrator.states import TERMINAL, check_transition
from netcoop.report.builder import build_failure_report, build_report
from netcoop.report.markdown import render_markdown
from netcoop.report.validate import validate_report
from netcoop.tools.toolbox import ToolBox
from netcoop.tools.topology import Topology, TopologyError, load_topology

_GOALS = {
    "performance_agent": "assess_performance",
    "infrastructure_agent": "assess_device_health",
    "connectivity_agent": "assess_connectivity_scope",
}


@dataclass
class IncidentResult:
    incident_id: str
    final_state: str
    report: dict[str, Any]
    markdown: str
    decision: Decision | None = None
    findings: dict[str, Finding] = field(default_factory=dict)
    missing_agents: list[str] = field(default_factory=list)
    issues: list[IngestIssue] = field(default_factory=list)


class _AgentFailure(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class Orchestrator:
    def __init__(
        self,
        store: LogStore,
        *,
        settings: Settings | None = None,
        params: DiagnosisParams | None = None,
        clock: Clock | None = None,
        fault_injection: dict[str, str] | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or load_settings()
        self.params = params or load_diagnosis_params()
        self.clock: Clock = clock or SystemClock()
        self.fault_injection = dict(fault_injection or {})
        self._state: dict[str, str | None] = {}

    # ------------------------------------------------------------------ state machine
    def _go(
        self,
        incident: str,
        new: str,
        *,
        trigger: str,
        message_id: str | None = None,
        detail: dict[str, Any] | None = None,
    ) -> None:
        current = self._state.get(incident)
        check_transition(current, new)
        self.store.append_transition(
            incident,
            current,
            new,
            trigger=trigger,
            at=self.clock.now(),
            message_id=message_id,
            detail=detail,
        )
        self._state[incident] = new

    # ------------------------------------------------------------------ entry point
    def run(
        self,
        raw: str | bytes,
        *,
        source: str = "cli",
        community: list[dict[str, Any]] | None = None,
        label: str | None = None,
    ) -> IncidentResult:
        cfg = self.settings.orchestration
        incident = self.store.register_incident(
            {"source": source, "mode": self.settings.mode, "label": label}, at=self.clock.now()
        )
        self._go(incident, "RECEIVED", trigger=source, detail={"label": label})
        self._go(incident, "VALIDATING", trigger="auto")
        result = ingest(raw, settings=self.settings)
        if result.bundle is None:
            errors = [f"{i.code}: {i.message}" for i in result.issues if i.severity == "fatal"]
            self._go(
                incident, "REJECTED", trigger="ingestion", detail={"code": result.rejection_code}
            )
            report = build_failure_report(
                incident,
                errors,
                mode=self.settings.mode,
                provenance="unknown (input rejected)",
                generated_at=self.clock.now(),
            )
            return self._finish(incident, report, result.issues)
        bundle = result.bundle
        topology, topo_note = self._topology(bundle)
        warnings = list(bundle.data_quality.warnings) + (["TOPOLOGY_MISSING"] if topo_note else [])
        acceptance = "READY_WITH_WARNINGS" if warnings else "READY"
        self._go(
            incident,
            acceptance,
            trigger="ingestion",
            detail={
                "warnings": warnings,
                "q": round(bundle.data_quality.q, 4),
                "topology": topo_note,
            },
        )

        bus = MessageBus(self.store, clock=self.clock, ids=IdFactory(namespace=incident))
        toolbox = ToolBox(bundle, topology, clock=self.clock)
        specialists = [
            PerformanceAgent(bus, lambda _i: toolbox, self.params),
            InfrastructureAgent(bus, lambda _i: toolbox, self.params),
            ConnectivityAgent(bus, lambda _i: toolbox, self.params),
        ]
        corr, rept = CorrelationAgent(bus, self.params), ReportingAgent(bus)
        handler: Handler
        for agent_id, handler in [
            *((a.agent_id, a.handle) for a in specialists),
            (corr.agent_id, corr.handle),
            (rept.agent_id, rept.handle),
        ]:
            fault = self.fault_injection.get(agent_id)
            if fault:
                handler = inject(handler, fault, bus, delay_s=cfg.specialist_deadline_s + 1.0)
            bus.register(agent_id, handler)

        findings, missing = self._phase1(incident, bus, bundle)
        community = community or []
        decision = self._correlate(incident, bus, bundle, findings, missing, community)
        if decision is None:
            self._go(incident, "FAILED", trigger="correlation_agent_failed")
            report = build_failure_report(
                incident,
                ["AGENT_FAILED: correlation_agent did not produce a decision after retry"],
                mode=self.settings.mode,
                provenance=bundle.provenance,
                generated_at=self.clock.now(),
                findings=findings,
            )
            return self._finish(incident, report, result.issues, findings=findings, missing=missing)
        top = next(h for h in decision.ranked if h.diagnosable)
        self._go(
            incident,
            "DECIDED",
            trigger="decision",
            detail={
                "decision": decision.decision,
                "top": top.cause_type,
                "entities": top.entities,
                "confidence": decision.confidence,
            },
        )
        self._go(incident, "REPORTING", trigger="auto")
        report, markdown, fallback = self._report(
            incident, bus, bundle, decision, findings, missing
        )
        final = "AWAITING_REVIEW" if report["recommended_actions"] else "COMPLETE"
        self._go(
            incident,
            final,
            trigger="fallback_report" if fallback else "report_ready",
            detail={"status": report["status"]},
        )
        return self._finish(
            incident,
            report,
            result.issues,
            markdown=markdown,
            decision=decision,
            findings=findings,
            missing=missing,
        )

    # ------------------------------------------------------------------ helpers
    def _topology(self, bundle: NormalizedBundle) -> tuple[Topology | None, str | None]:
        if bundle.topology_ref is None:
            return None, "bundle names no topology_ref"
        try:
            return load_topology(bundle.topology_ref), None
        except (TopologyError, ValueError) as exc:
            return None, str(exc)

    def _window(self, bundle: NormalizedBundle) -> TimeWindow:
        return bundle.window

    def _ask(
        self, bus: MessageBus, sent: ParsedMessage, pool: cf.ThreadPoolExecutor | None
    ) -> cf.Future[ParsedMessage]:
        if pool is None:
            fut: cf.Future[ParsedMessage] = cf.Future()
            try:
                fut.set_result(bus.deliver(sent))
            except Exception as exc:  # surfaced through the future like a pooled call
                fut.set_exception(exc)
            return fut
        return pool.submit(bus.deliver, sent)

    def _outcome(self, fut: cf.Future[ParsedMessage], timeout: float) -> ParsedMessage:
        try:
            reply = fut.result(timeout=timeout)
        except cf.TimeoutError as exc:
            raise _AgentFailure("AGENT_TIMEOUT", f"no reply within {timeout:g}s") from exc
        except MessageValidationError as exc:
            raise _AgentFailure(exc.code, exc.detail[:300]) from exc
        except Exception as exc:
            raise _AgentFailure("AGENT_FAILED", f"{type(exc).__name__}: {exc}") from exc
        if isinstance(reply.payload, AgentError):
            raise _AgentFailure(reply.payload.code, reply.payload.message)
        return reply

    def _phase1(
        self, incident: str, bus: MessageBus, bundle: NormalizedBundle
    ) -> tuple[dict[str, Finding], list[str]]:
        cfg = self.settings.orchestration
        deadline = cfg.specialist_deadline_s
        findings: dict[str, Finding] = {}
        to_run: list[str] = list(SPECIALIST_AGENTS)
        pool = cf.ThreadPoolExecutor(max_workers=3) if cfg.parallel_specialists else None
        # Sequential mode still needs a worker to enforce deadlines.
        timer_pool = None if pool else cf.ThreadPoolExecutor(max_workers=1)
        try:
            for attempt in range(cfg.agent_retries + 1):
                sent: dict[str, ParsedMessage] = {}
                for agent in to_run:  # fixed order -> deterministic request ids
                    sent[agent] = bus.send_request(
                        sender="orchestrator",
                        recipient=agent,  # type: ignore[arg-type]
                        message_type="task_request",
                        payload=TaskRequest(
                            goal=_GOALS[agent],
                            scope_entities=list(bundle.entities),
                            window=self._window(bundle),
                            tool_budget=cfg.tool_budgets.get(agent, 20),
                            deadline_s=deadline,
                            context={"attempt": attempt + 1},
                        ),
                        incident_id=incident,
                    )
                if attempt == 0:
                    self._go(
                        incident,
                        "DISPATCHED",
                        trigger="tasks_sent",
                        detail={"agents": to_run, "deadline_s": deadline},
                    )
                    self._go(incident, "COLLECTING", trigger="auto")
                failed: list[str] = []
                if pool is not None:
                    futures = {a: self._ask(bus, sent[a], pool) for a in to_run}
                    outcomes = {}
                    for a in to_run:
                        try:
                            outcomes[a] = self._outcome(futures[a], deadline)
                        except _AgentFailure as f:
                            outcomes[a] = f  # type: ignore[assignment]
                else:
                    outcomes = {}
                    for a in to_run:
                        assert timer_pool is not None
                        try:
                            outcomes[a] = self._outcome(
                                timer_pool.submit(bus.deliver, sent[a]), deadline
                            )
                        except _AgentFailure as f:
                            outcomes[a] = f  # type: ignore[assignment]
                for a in to_run:
                    out = outcomes[a]
                    if isinstance(out, _AgentFailure):
                        failed.append(a)
                        bus.notify(
                            sender="orchestrator",
                            recipient=a,  # type: ignore[arg-type]
                            message_type="agent_error",
                            payload=AgentError(
                                code=out.code,
                                message=f"attempt {attempt + 1}: {out.detail}",
                                recoverable=attempt < cfg.agent_retries,
                            ),
                            incident_id=incident,
                            in_reply_to=sent[a].envelope.message_id,
                            status="error",
                        )
                        self._go(
                            incident,
                            "COLLECTING",
                            trigger="agent_error",
                            message_id=sent[a].envelope.message_id,
                            detail={"agent": a, "agent_error": out.code, "attempt": attempt + 1},
                        )
                    else:
                        assert isinstance(out.payload, Finding)
                        findings[a] = out.payload
                to_run = failed
                if not to_run:
                    break
        finally:
            for p in (pool, timer_pool):
                if p is not None:
                    p.shutdown(wait=False, cancel_futures=True)
        missing = sorted(to_run)
        return {a: findings[a] for a in SPECIALIST_AGENTS if a in findings}, missing

    def _request_with_retry(
        self, bus: MessageBus, incident: str, recipient: AgentId, payload: Any
    ) -> ParsedMessage | None:
        for attempt in range(self.settings.orchestration.agent_retries + 1):
            sent = bus.send_request(
                sender="orchestrator",
                recipient=recipient,
                message_type="task_request",
                payload=payload,
                incident_id=incident,
            )
            try:
                return self._outcome(self._ask(bus, sent, None), timeout=60)
            except _AgentFailure as f:
                bus.notify(
                    sender="orchestrator",
                    recipient=recipient,
                    message_type="agent_error",
                    payload=AgentError(
                        code=f.code, message=f"attempt {attempt + 1}: {f.detail}", recoverable=True
                    ),
                    incident_id=incident,
                    in_reply_to=sent.envelope.message_id,
                    status="error",
                )
        return None

    def _correlate(
        self,
        incident: str,
        bus: MessageBus,
        bundle: NormalizedBundle,
        findings: dict[str, Finding],
        missing: list[str],
        community: list[dict[str, Any]],
    ) -> Decision | None:
        cfg = self.settings.orchestration
        clarifications: list[dict[str, Any]] = []
        self._go(
            incident,
            "CORRELATING",
            trigger="all_specialists_missing" if len(missing) == 3 else "findings_collected",
            detail={"findings": sorted(findings), "missing": missing},
        )
        for round_no in range(1, cfg.max_clarification_rounds + 2):
            ctx = correlation_context(
                bundle,
                findings,
                missing_agents=missing,
                clarifications=clarifications,
                round_no=round_no,
                max_rounds=cfg.max_clarification_rounds,
                community=community,
            )
            reply = self._request_with_retry(
                bus,
                incident,
                "correlation_agent",
                TaskRequest(
                    goal="correlate",
                    scope_entities=list(bundle.entities),
                    window=bundle.window,
                    tool_budget=0,
                    deadline_s=60,
                    context=ctx,
                ),
            )
            if reply is None:
                return None
            if isinstance(reply.payload, Decision):
                return reply.payload
            if not isinstance(reply.payload, ClarificationRequest):
                return None
            q = reply.payload
            self._go(
                incident,
                "CLARIFYING",
                trigger="clarification_request",
                message_id=reply.envelope.message_id,
                detail={"question_type": q.question_type, "target": q.target, "round": q.round},
            )
            try:
                answer = bus.request(
                    sender="orchestrator",
                    recipient=q.target,
                    message_type="clarification_request",
                    payload=q,
                    incident_id=incident,
                    in_reply_to=reply.envelope.message_id,
                )
                response = answer.envelope.payload
                if answer.envelope.message_type != "clarification_response":
                    response = {"answered": False, "reason": "target replied with an error"}
            except Exception as exc:  # unanswered questions are recorded, never fatal
                response = {"answered": False, "reason": f"{type(exc).__name__}: {exc}"}
            clarifications.append({"request": q.model_dump(mode="json"), "response": response})
            self._go(incident, "CORRELATING", trigger="clarification_answered")
        return None

    def _report(
        self,
        incident: str,
        bus: MessageBus,
        bundle: NormalizedBundle,
        decision: Decision,
        findings: dict[str, Finding],
        missing: list[str],
    ) -> tuple[dict[str, Any], str, bool]:
        generated = self.clock.now().isoformat()
        ctx = reporting_context(
            incident,
            bundle,
            decision,
            findings,
            mode=self.settings.mode,
            missing_agents=missing,
            generated_at=generated,
        )
        reply = self._request_with_retry(
            bus,
            incident,
            "reporting_agent",
            TaskRequest(
                goal="report",
                scope_entities=list(bundle.entities),
                window=bundle.window,
                tool_budget=0,
                deadline_s=60,
                context=ctx,
            ),
        )
        if reply is not None and isinstance(reply.payload, ReportReady):
            return reply.payload.report, reply.payload.markdown or "", False
        # Deterministic fallback builder (doc 04 §5): same content, no agent involved.
        report = build_report(
            incident,
            decision,
            findings,
            data_quality=ctx["data_quality"],
            provenance=bundle.provenance,
            mode=self.settings.mode,
            missing_agents=missing,
            generated_at=self.clock.now(),
        )
        problems = validate_report(
            report,
            observation_ids={o.observation_id for f in findings.values() for o in f.observations},
            finding_agents=set(findings),
        )
        if problems:  # pragma: no cover - would be a builder bug
            raise RuntimeError("fallback report invalid: " + "; ".join(problems))
        return report, render_markdown(report), True

    def _finish(
        self,
        incident: str,
        report: dict[str, Any],
        issues: list[IngestIssue],
        *,
        markdown: str | None = None,
        decision: Decision | None = None,
        findings: dict[str, Finding] | None = None,
        missing: list[str] | None = None,
    ) -> IncidentResult:
        md = markdown if markdown is not None else render_markdown(report)
        self.store.append_report(incident, report, md, at=self.clock.now())
        return IncidentResult(
            incident_id=incident,
            final_state=self._state.get(incident) or "UNKNOWN",
            report=report,
            markdown=md,
            decision=decision,
            findings=findings or {},
            missing_agents=missing or [],
            issues=issues,
        )

    def state_of(self, incident: str) -> str | None:
        return self._state.get(incident)

    @staticmethod
    def is_terminal(state: str | None) -> bool:
        return state in TERMINAL

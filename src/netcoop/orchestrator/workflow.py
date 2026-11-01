"""Deterministic orchestrator (doc 04) with durable, resumable workflow state.

One incident flows

``RECEIVED → VALIDATING → READY[_WITH_WARNINGS] → DISPATCHED → COLLECTING →
CORRELATING (⇄ CLARIFYING) → DECIDED → REPORTING → AWAITING_REVIEW | COMPLETE``,

with ``REJECTED`` and ``FAILED`` exits. Every transition and message is logged.

**Determinism (doc 04 §4).** Requests are built in this thread in a fixed agent order,
replies get ids derived from their request, findings are consumed in fixed order and
clarification rounds are sequential, so parallel and sequential runs log the same messages.

**Persistent state / pause-resume (component 10).** The workflow writes append-only
*checkpoints* - the input, each specialist finding as it arrives, the phase-1 outcome,
each clarification answer, the decision - always *before* the transition that follows.
:meth:`Orchestrator.resume` (typically in a new process) rebuilds the run from them and
continues from the last recorded state, re-dispatching only work that never completed.
``pause_after=STATE`` stops cleanly once a state is entered.
"""

from __future__ import annotations

import base64
import concurrent.futures as cf
import json
from collections.abc import Callable
from contextlib import ExitStack
from dataclasses import dataclass, field
from functools import partial
from typing import Any

from netcoop.agents.connectivity import ConnectivityAgent
from netcoop.agents.correlation import CorrelationAgent, correlation_context
from netcoop.agents.infrastructure import InfrastructureAgent
from netcoop.agents.performance import PerformanceAgent
from netcoop.agents.reporting import ReportingAgent, reporting_context
from netcoop.config.settings import Settings, load_settings
from netcoop.core.blocks import IncidentContext, TimeWindow
from netcoop.core.bus import GuardViolationError, Handler, MessageBus
from netcoop.core.guard import ConversationGuard
from netcoop.core.ids import Clock, IdFactory, SystemClock
from netcoop.core.log_store import LogStore
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    CommunityCandidate,
    ConflictReport,
    ConflictResponse,
    Decision,
    Finding,
    MessageValidationError,
    ParsedMessage,
    ReportReady,
    TaskRequest,
)
from netcoop.core.snapshot import DataSnapshot, take_snapshot
from netcoop.core.vocab import SPECIALIST_AGENTS, AgentId
from netcoop.diagnosis.params import DiagnosisParams, load_diagnosis_params
from netcoop.ingestion.issues import IngestIssue
from netcoop.ingestion.models import NormalizedBundle
from netcoop.ingestion.normalize import ingest, parse_timestamp
from netcoop.llm.gateway import LLMGateway, NullProvider
from netcoop.orchestrator.faults import SimulatedCrash, inject
from netcoop.orchestrator.states import RESUMABLE, TERMINAL, check_transition
from netcoop.report.builder import build_failure_report, build_report
from netcoop.report.markdown import render_markdown
from netcoop.report.validate import validate_report
from netcoop.tools.toolbox import ToolBox
from netcoop.tools.topology import Topology, TopologyError, load_topology

__all__ = ["IncidentResult", "Orchestrator", "SimulatedCrash"]

_GOALS = {
    "performance_agent": "assess_performance",
    "infrastructure_agent": "assess_device_health",
    "connectivity_agent": "assess_connectivity_scope",
}
_PHASE1_STATES = {"READY", "READY_WITH_WARNINGS", "DISPATCHED", "COLLECTING"}


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
    paused: bool = False


class _AgentFailure(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


class _Paused(Exception):
    pass


@dataclass
class _Run:
    """Everything one incident needs; rebuilt from checkpoints on resume."""

    incident: str
    raw: bytes
    community: list[dict[str, Any]]
    community_errors: list[str] = field(default_factory=list)
    label: str = ""
    issues: list[IngestIssue] = field(default_factory=list)
    bundle: NormalizedBundle | None = None
    topology: Topology | None = None
    topo_note: str | None = None
    bus: MessageBus | None = None
    resources: ExitStack = field(default_factory=ExitStack)
    findings: dict[str, Finding] = field(default_factory=dict)
    missing: list[str] | None = None
    clarifications: list[dict[str, Any]] = field(default_factory=list)
    decision: Decision | None = None
    snapshot: DataSnapshot | None = None


class Orchestrator:
    def __init__(
        self,
        store: LogStore,
        *,
        settings: Settings | None = None,
        params: DiagnosisParams | None = None,
        clock: Clock | None = None,
        fault_injection: dict[str, str] | None = None,
        llm: LLMGateway | None = None,
    ) -> None:
        self.store = store
        self.settings = settings or load_settings()
        self.params = params or load_diagnosis_params()
        self.clock: Clock = clock or SystemClock()
        self.fault_injection = dict(fault_injection or {})
        # LLM is optional and off by default (CD-1). If enabled without a configured
        # provider, the null provider makes every attempt fall back to the template.
        if llm is None and self.settings.features.llm:
            llm = LLMGateway(NullProvider(), enabled=True)
        self.llm = llm
        self._state: dict[str, str | None] = {}
        self._pause_after: str | None = None

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
        check_transition(current, new, resume=trigger == "resume")
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
        if self._pause_after == new and trigger != "resume":
            raise _Paused(new)

    def _checkpoint(self, run: _Run, kind: str, data: dict[str, Any]) -> None:
        self.store.append_checkpoint(run.incident, kind, data, at=self.clock.now())

    def state_of(self, incident: str) -> str | None:
        transitions = self.store.transitions(incident)
        return transitions[-1].to_state if transitions else None

    def resumable(self) -> list[str]:
        return [i for i in self.store.list_incidents() if self.state_of(i) in RESUMABLE]

    @staticmethod
    def is_terminal(state: str | None) -> bool:
        return state in TERMINAL

    # ------------------------------------------------------------------ entry points
    def run(
        self,
        raw: str | bytes,
        *,
        source: str = "cli",
        community: list[dict[str, Any]] | None = None,
        label: str | None = None,
        pause_after: str | None = None,
    ) -> IncidentResult:
        data = raw.encode("utf-8") if isinstance(raw, str) else raw
        incident = self.store.register_incident(
            {"source": source, "mode": self.settings.mode, "label": label},
            at=self.clock.now(),
            prefix=self.settings.protocol.incident_prefix,
        )
        run = _Run(
            incident=incident, raw=data, community=list(community or []), label=label or source
        )
        self._checkpoint(
            run,
            "input",
            {
                "raw_b64": base64.b64encode(data).decode("ascii"),
                "community": run.community,
                "source": source,
                "label": label,
            },
        )
        self._pause_after = pause_after
        try:
            self._go(incident, "RECEIVED", trigger=source, detail={"label": label})
            return self._drive(run)
        except _Paused:
            return self._paused(run)
        finally:
            self._pause_after = None

    def resume(self, incident: str, *, pause_after: str | None = None) -> IncidentResult:
        if incident not in self.store.list_incidents():
            raise KeyError(f"unknown incident {incident}")
        state = self.state_of(incident)
        self._state[incident] = state
        if state not in RESUMABLE:  # finished, rejected, failed or waiting for a human
            stored = self.store.latest_report(incident)
            report, md = stored if stored else ({}, "")
            return IncidentResult(incident, state or "UNKNOWN", report, md)
        run = self._rebuild(incident)
        self._pause_after = pause_after
        try:
            self._go(incident, state or "RECEIVED", trigger="resume")
            return self._drive(run)
        except _Paused:
            return self._paused(run)
        finally:
            self._pause_after = None

    def _rebuild(self, incident: str) -> _Run:
        cps = self.store.checkpoints(incident)
        inp = next(c["data"] for c in cps if c["kind"] == "input")
        run = _Run(
            incident=incident,
            raw=base64.b64decode(inp["raw_b64"]),
            community=list(inp.get("community", [])),
            label=inp.get("label") or inp.get("source") or "",
        )
        for c in cps:
            kind, data = c["kind"], c["data"]
            if kind.startswith("finding:"):
                run.findings[kind.split(":", 1)[1]] = Finding.model_validate(data["finding"])
            elif kind == "phase1":
                run.missing = list(data["missing"])
            elif kind == "clarification":
                run.clarifications.append(data)
            elif kind == "decision":
                run.decision = Decision.model_validate(data["decision"])
        return run

    def _paused(self, run: _Run) -> IncidentResult:
        state = self._state.get(run.incident) or "UNKNOWN"
        return IncidentResult(
            incident_id=run.incident,
            final_state=state,
            report={},
            markdown="",
            findings=dict(run.findings),
            paused=True,
        )

    # ------------------------------------------------------------------ the workflow
    def _drive(self, run: _Run) -> IncidentResult:
        with run.resources:  # closes the MCP session (if any) however the run ends
            return self._drive_stages(run)

    def _drive_stages(self, run: _Run) -> IncidentResult:
        incident = run.incident
        state = self._state.get(incident)
        if state in ("RECEIVED", "VALIDATING"):
            if state == "RECEIVED":
                self._go(incident, "VALIDATING", trigger="auto")
            rejected = self._validate(run)
            if rejected is not None:
                return rejected
            assert run.bundle is not None
            warnings = list(run.bundle.data_quality.warnings) + (
                ["TOPOLOGY_MISSING"] if run.topo_note else []
            )
            acceptance = "READY_WITH_WARNINGS" if warnings else "READY"
            snapshot = self._take_snapshot(run, acceptance)
            self._go(
                incident,
                acceptance,
                trigger="ingestion",
                detail={
                    "warnings": warnings,
                    "q": round(run.bundle.data_quality.q, 4),
                    "topology": run.topo_note,
                    "snapshot_id": snapshot.snapshot_id,
                },
            )
        elif self._validate(run) is not None:  # pragma: no cover - input was accepted before
            raise RuntimeError("stored input no longer validates")
        else:
            stored = [
                c["data"] for c in self.store.checkpoints(incident) if c["kind"] == "snapshot"
            ]
            run.snapshot = (
                DataSnapshot.model_validate(stored[-1])
                if stored
                else self._take_snapshot(run, run.bundle.data_quality.acceptance)  # type: ignore[union-attr]
            )
        self._setup_agents(run)
        self._admit_community(run)

        if self._state.get(incident) in _PHASE1_STATES:
            self._phase1(run)
        if self._state.get(incident) in ("CORRELATING", "CLARIFYING", "COLLECTING"):
            decision = self._correlate(run)
            if decision is None:
                self._go(incident, "FAILED", trigger="correlation_agent_failed")
                report = build_failure_report(
                    incident,
                    ["AGENT_FAILED: correlation_agent did not produce a decision after retry"],
                    mode=self.settings.mode,
                    provenance=run.bundle.provenance if run.bundle else "unknown",
                    generated_at=self.clock.now(),
                    findings=run.findings,
                )
                return self._finish(run, report)
            run.decision = decision
            self._checkpoint(run, "decision", {"decision": decision.model_dump(mode="json")})
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
        if self._state.get(incident) == "DECIDED":
            self._go(incident, "REPORTING", trigger="auto")
        assert run.decision is not None
        report, markdown, fallback = self._report(run)
        final = "AWAITING_REVIEW" if report["recommended_actions"] else "COMPLETE"
        self._go(
            incident,
            final,
            trigger="fallback_report" if fallback else "report_ready",
            detail={"status": report["status"]},
        )
        return self._finish(run, report, markdown=markdown)

    def _admit_community(self, run: _Run) -> None:
        """Extension A input (doc 04 §8): each valid candidate enters through the protocol
        as a ``community_candidate`` message. A malformed entry is dropped and recorded -
        an extension problem must never break or change the core run (T-ISO-02)."""
        assert run.bus is not None
        valid: list[dict[str, Any]] = []
        payloads: list[CommunityCandidate] = []
        run.community_errors = []
        for entry in run.community:
            try:
                start, end = parse_timestamp(entry["start"]), parse_timestamp(entry["end"])
                if start is None or end is None:
                    raise ValueError("start/end must be ISO timestamps with a timezone")
                payloads.append(
                    CommunityCandidate(
                        candidate_id=str(entry["candidate_id"]),
                        zone=str(entry["zone"]),
                        symptom_categories=list(entry.get("symptom_categories", [])),
                        window=TimeWindow(start=start, end=end),
                        complaint_count=int(entry["complaint_count"]),
                        distinct_reporters=int(entry["distinct_reporters"]),
                    )
                )
                valid.append(entry)
            except (KeyError, TypeError, ValueError) as exc:
                cid = entry.get("candidate_id", "?") if isinstance(entry, dict) else "?"
                run.community_errors.append(
                    f"Community input {cid} ignored (invalid: {str(exc).splitlines()[0]}); "
                    "the core diagnosis is unaffected."
                )
        run.community = valid
        already = any(
            m.message_type == "community_candidate" for m in self.store.messages(run.incident)
        )
        if not already:
            for payload in payloads:
                try:
                    run.bus.notify(
                        sender="community_module",
                        recipient="orchestrator",
                        message_type="community_candidate",
                        payload=payload,
                        incident_id=run.incident,
                    )
                except GuardViolationError as exc:  # e.g. EXTENSION_DISABLED: never fatal
                    run.community_errors.append(
                        f"Community input {payload.candidate_id} not admitted ({exc.code}: "
                        f"{exc.detail}); the core diagnosis is unaffected."
                    )
        admitted = {
            json.loads(m.raw_json)["payload"]["candidate_id"]
            for m in self.store.messages(run.incident)
            if m.valid and m.message_type == "community_candidate"
        }
        run.community = [e for e in run.community if str(e["candidate_id"]) in admitted]

    def _take_snapshot(self, run: _Run, acceptance: str) -> DataSnapshot:
        """Fingerprint the data every agent will analyse; checkpointed so a resumed run
        reuses the identical snapshot (protocol 1.1, doc 05 §1)."""
        assert run.bundle is not None
        snapshot = take_snapshot(
            run.bundle,
            run.topology,
            settings=self.settings,
            params=self.params,
            source_label=run.label,
            clock=self.clock,
            acceptance=acceptance,
        )
        self._checkpoint(run, "snapshot", snapshot.model_dump(mode="json"))
        run.snapshot = snapshot
        return snapshot

    def _validate(self, run: _Run) -> IncidentResult | None:
        result = ingest(run.raw, settings=self.settings)
        run.issues = result.issues
        if result.bundle is None:
            errors = [f"{i.code}: {i.message}" for i in result.issues if i.severity == "fatal"]
            self._go(
                run.incident,
                "REJECTED",
                trigger="ingestion",
                detail={"code": result.rejection_code},
            )
            report = build_failure_report(
                run.incident,
                errors,
                mode=self.settings.mode,
                provenance="unknown (input rejected)",
                generated_at=self.clock.now(),
            )
            return self._finish(run, report)
        run.bundle = result.bundle
        run.topology, run.topo_note = self._topology(result.bundle)
        return None

    def _topology(self, bundle: NormalizedBundle) -> tuple[Topology | None, str | None]:
        if bundle.topology_ref is None:
            return None, "bundle names no topology_ref"
        try:
            return load_topology(bundle.topology_ref), None
        except (TopologyError, ValueError) as exc:
            return None, str(exc)

    def _setup_agents(self, run: _Run) -> None:
        assert run.bundle is not None
        cfg = self.settings.orchestration
        ids = IdFactory(namespace=run.incident)
        ids.seed("MSG", self.store.max_message_seq(run.incident))  # continue after restart
        bus = MessageBus(
            self.store,
            clock=self.clock,
            ids=ids,
            snapshot=run.snapshot,
            max_message_bytes=self.settings.protocol.max_message_bytes,
            guard=ConversationGuard(
                max_clarification_rounds=cfg.max_clarification_rounds,
                extensions=[name for name, on in self.settings.features.model_dump().items() if on],
            ),
            incident_state=self._state.get,
        )
        self.last_bus: MessageBus | None = bus  # the live bus, for inspection and demos
        toolbox: Any
        if cfg.tool_transport == "mcp":
            # Imported here: the MCP server itself imports the scenario runner (and thus
            # this module), so a top-level import would be circular.
            from netcoop.mcp.adapter import McpToolBox
            from netcoop.mcp.server import build_server

            # Component 8: agents read through the MCP server, which serves this incident
            # from its stored input checkpoint.
            toolbox = run.resources.enter_context(
                McpToolBox(build_server(self.store), source=run.incident, clock=self.clock)
            )
        else:
            toolbox = ToolBox(run.bundle, run.topology, clock=self.clock)
        specialists = [
            PerformanceAgent(bus, lambda _i: toolbox, self.params),
            InfrastructureAgent(bus, lambda _i: toolbox, self.params),
            ConnectivityAgent(bus, lambda _i: toolbox, self.params),
        ]
        corr, rept = CorrelationAgent(bus, self.params), ReportingAgent(bus, llm=self.llm)
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
        run.bus = bus

    # ------------------------------------------------------------------ agent calls
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

    def _outcome(
        self,
        fut: cf.Future[Any],
        timeout: float,
        accept: Callable[[Any], ParsedMessage] | None = None,
    ) -> ParsedMessage:
        """Wait for a reply. With ``accept``, the future yields the raw reply and it is
        validated and logged HERE, in the caller's thread - so replies from parallel
        specialists are logged (and numbered) in a fixed, deterministic order."""
        try:
            raw_reply = fut.result(timeout=timeout)
            reply: ParsedMessage = accept(raw_reply) if accept is not None else raw_reply
        except cf.TimeoutError as exc:
            raise _AgentFailure("AGENT_TIMEOUT", f"no reply within {timeout:g}s") from exc
        except MessageValidationError as exc:
            raise _AgentFailure(exc.code, exc.detail[:300]) from exc
        except Exception as exc:
            raise _AgentFailure("AGENT_FAILED", f"{type(exc).__name__}: {exc}") from exc
        if isinstance(reply.payload, AgentError):
            raise _AgentFailure(reply.payload.code, reply.payload.message)
        return reply

    def _phase1(self, run: _Run) -> None:
        assert run.bus is not None and run.bundle is not None
        bus, bundle, incident = run.bus, run.bundle, run.incident
        cfg = self.settings.orchestration
        deadline = cfg.specialist_deadline_s
        state = self._state.get(incident)
        to_run = [a for a in SPECIALIST_AGENTS if a not in run.findings]
        pool = cf.ThreadPoolExecutor(max_workers=3) if cfg.parallel_specialists else None
        timer_pool = None if pool else cf.ThreadPoolExecutor(max_workers=1)
        try:
            for attempt in range(cfg.agent_retries + 1):
                if not to_run:
                    break
                sent: dict[str, ParsedMessage] = {}
                for agent in to_run:  # fixed order -> deterministic request ids
                    sent[agent] = bus.send_request(
                        sender="orchestrator",
                        recipient=agent,
                        message_type="task_request",
                        payload=TaskRequest(
                            goal=_GOALS[agent],
                            scope_entities=list(bundle.entities),
                            window=bundle.window,
                            tool_budget=cfg.tool_budgets.get(agent, 20),
                            deadline_s=deadline,
                            context={"attempt": attempt + 1},
                            **self._task_meta(run, "investigate"),
                        ),
                        incident_id=incident,
                    )
                if attempt == 0 and state in ("READY", "READY_WITH_WARNINGS"):
                    self._go(
                        incident,
                        "DISPATCHED",
                        trigger="tasks_sent",
                        detail={
                            "agents": to_run,
                            "deadline_s": deadline,
                            "tool_transport": cfg.tool_transport,
                        },
                    )
                if attempt == 0 and state in ("READY", "READY_WITH_WARNINGS", "DISPATCHED"):
                    self._go(incident, "COLLECTING", trigger="auto")
                # Handlers run in parallel; replies are validated, logged and numbered
                # below in fixed agent order (deterministic seq, protocol 1.1).
                futures = (
                    {a: pool.submit(bus.call_handler, sent[a]) for a in to_run}
                    if pool is not None
                    else {}
                )
                failed: list[AgentId] = []
                for a in to_run:  # fixed order; each finding is made durable on arrival
                    fut = futures[a] if pool is not None else _submit(timer_pool, bus, sent[a])
                    try:
                        out = self._outcome(fut, deadline, partial(bus.accept_reply, sent=sent[a]))
                    except _AgentFailure as f:
                        failed.append(a)
                        self._agent_error(run, a, sent[a], f, attempt)
                        continue
                    assert isinstance(out.payload, Finding)
                    run.findings[a] = out.payload
                    self._checkpoint(
                        run, f"finding:{a}", {"finding": out.payload.model_dump(mode="json")}
                    )
                to_run = failed
        finally:
            for p in (pool, timer_pool):
                if p is not None:
                    p.shutdown(wait=False, cancel_futures=True)
        run.missing = sorted(to_run)
        self._checkpoint(run, "phase1", {"missing": run.missing})
        run.findings = {a: run.findings[a] for a in SPECIALIST_AGENTS if a in run.findings}

    def _task_meta(self, run: _Run, kind: str, inputs: tuple[str, ...] = ()) -> dict[str, Any]:
        """Protocol 1.1 task fields: a per-incident task id, the task kind, the incident
        context, and REFERENCES (message ids) to the earlier messages the task works from."""
        assert run.bundle is not None
        logged = [m for m in self.store.messages(run.incident) if m.valid]
        n = sum(1 for m in logged if m.message_type == "task_request") + 1
        return {
            "task_id": f"TASK-{n:04d}",
            "task_kind": kind,
            "input_message_ids": [m.message_id for m in logged if m.message_type in inputs],
            "incident_context": IncidentContext(
                description=run.label,
                trigger="telemetry_bundle",
                incident_time=run.bundle.window.end,
            ),
        }

    def _agent_error(
        self, run: _Run, agent: str, sent: ParsedMessage, failure: _AgentFailure, attempt: int
    ) -> None:
        assert run.bus is not None
        run.bus.notify(
            sender="orchestrator",
            recipient=agent,  # type: ignore[arg-type]
            message_type="agent_error",
            payload=AgentError(
                code=failure.code,
                message=f"attempt {attempt + 1}: {failure.detail}",
                recoverable=attempt < self.settings.orchestration.agent_retries,
                related_message_id=sent.envelope.message_id,
            ),
            incident_id=run.incident,
            in_reply_to=sent.envelope.message_id,
            status="error",
        )
        self._go(
            run.incident,
            "COLLECTING",
            trigger="agent_error",
            message_id=sent.envelope.message_id,
            detail={"agent": agent, "agent_error": failure.code, "attempt": attempt + 1},
        )

    def _request_with_retry(
        self, run: _Run, recipient: AgentId, payload: Any
    ) -> ParsedMessage | None:
        assert run.bus is not None
        bus = run.bus
        for attempt in range(self.settings.orchestration.agent_retries + 1):
            sent = bus.send_request(
                sender="orchestrator",
                recipient=recipient,
                message_type="task_request",
                payload=payload,
                incident_id=run.incident,
            )
            try:
                return self._outcome(self._ask(bus, sent, None), timeout=60)
            except _AgentFailure as f:
                bus.notify(
                    sender="orchestrator",
                    recipient=recipient,
                    message_type="agent_error",
                    payload=AgentError(
                        code=f.code,
                        message=f"attempt {attempt + 1}: {f.detail}",
                        recoverable=True,
                        related_message_id=sent.envelope.message_id,
                    ),
                    incident_id=run.incident,
                    in_reply_to=sent.envelope.message_id,
                    status="error",
                )
        return None

    def _correlate(self, run: _Run) -> Decision | None:
        assert run.bus is not None and run.bundle is not None
        bus, bundle, incident = run.bus, run.bundle, run.incident
        cfg = self.settings.orchestration
        missing = run.missing or []
        state = self._state.get(incident)
        if state == "COLLECTING":
            self._go(
                incident,
                "CORRELATING",
                trigger="all_specialists_missing" if len(missing) == 3 else "findings_collected",
                detail={"findings": sorted(run.findings), "missing": missing},
            )
        elif state == "CLARIFYING":
            self._go(incident, "CORRELATING", trigger="clarification_answered")
        while len(run.clarifications) <= cfg.max_clarification_rounds:
            ctx = correlation_context(
                bundle,
                run.findings,
                missing_agents=missing,
                clarifications=run.clarifications,
                round_no=len(run.clarifications) + 1,
                max_rounds=cfg.max_clarification_rounds,
                community=run.community,
            )
            reply = self._request_with_retry(
                run,
                "correlation_agent",
                TaskRequest(
                    goal="correlate",
                    scope_entities=list(bundle.entities),
                    window=bundle.window,
                    tool_budget=0,
                    deadline_s=60,
                    context=ctx,
                    **self._task_meta(run, "correlate", ("finding",)),
                ),
            )
            if reply is None:
                return None
            if isinstance(reply.payload, Decision):
                return reply.payload
            if isinstance(reply.payload, ConflictReport):
                self._relay_conflict(run, reply)
                continue
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
            entry = {"request": q.model_dump(mode="json"), "response": response}
            run.clarifications.append(entry)
            self._checkpoint(run, "clarification", entry)
            self._go(incident, "CORRELATING", trigger="clarification_answered")
        return None

    def _relay_conflict(self, run: _Run, reply: ParsedMessage) -> None:
        """Protocol 1.2: relay the correlation agent's conflict_report to the party it names
        and record the exchange exactly like a clarification round (same context entry), so
        the correlation agent's resolution logic is unchanged."""
        assert run.bus is not None and isinstance(reply.payload, ConflictReport)
        report, incident = reply.payload, run.incident
        self._go(
            incident,
            "CLARIFYING",
            trigger="conflict_report",
            message_id=reply.envelope.message_id,
            detail={
                "conflict_id": report.conflict_id,
                "target": report.target,
                "round": report.round,
            },
        )
        response: dict[str, Any]
        try:
            answer = run.bus.request(
                sender="orchestrator",
                recipient=report.target,
                message_type="conflict_report",
                payload=report,
                incident_id=incident,
                in_reply_to=reply.envelope.message_id,
            )
            if isinstance(answer.payload, ConflictResponse):
                r = answer.payload
                response = {
                    "answered": r.stance != "cannot_assess" and bool(r.observations),
                    "observations": [o.model_dump(mode="json") for o in r.observations],
                    "reason": r.note,
                    "stance": r.stance,
                    "conflict_id": r.conflict_id,
                }
            else:
                response = {"answered": False, "reason": "target replied with an error"}
        except Exception as exc:  # unanswered conflicts are recorded, never fatal
            response = {"answered": False, "reason": f"{type(exc).__name__}: {exc}"}
        params = {k: v for k, v in report.recheck.items() if k != "question_type"}
        entry = {
            "request": {
                "question_type": report.recheck.get("question_type", "recheck_metric"),
                "target": report.target,
                "parameters": params,
                "reason": "conflict",
                "round": report.round,
                "conflict_id": report.conflict_id,
            },
            "response": response,
        }
        run.clarifications.append(entry)
        self._checkpoint(run, "clarification", entry)
        self._go(incident, "CORRELATING", trigger="conflict_answered")

    def _report(self, run: _Run) -> tuple[dict[str, Any], str, bool]:
        assert run.bundle is not None and run.decision is not None
        bundle, decision = run.bundle, run.decision
        missing = run.missing or []
        ctx = reporting_context(
            run.incident,
            bundle,
            decision,
            run.findings,
            mode=self.settings.mode,
            missing_agents=missing,
            generated_at=self.clock.now().isoformat(),
            community=run.community,
            community_errors=run.community_errors,
            # Identity of the analysed data; its wall-clock created_at stays in the
            # checkpoint so reports remain reproducible across runs.
            data_snapshot=(
                run.snapshot.model_dump(mode="json", exclude={"created_at"})
                if run.snapshot
                else None
            ),
        )
        reply = self._request_with_retry(
            run,
            "reporting_agent",
            TaskRequest(
                goal="report",
                scope_entities=list(bundle.entities),
                window=bundle.window,
                tool_budget=0,
                deadline_s=60,
                context=ctx,
                **self._task_meta(run, "report", ("finding", "decision")),
            ),
        )
        if reply is not None and isinstance(reply.payload, ReportReady):
            return reply.payload.report, reply.payload.markdown or "", False
        # Deterministic fallback builder (doc 04 §5): same content, no agent involved.
        report = build_report(
            run.incident,
            decision,
            run.findings,
            data_quality=ctx["data_quality"],
            provenance=bundle.provenance,
            mode=self.settings.mode,
            missing_agents=missing,
            generated_at=self.clock.now(),
            community=run.community,
            community_errors=run.community_errors,
            data_snapshot=ctx["data_snapshot"],
        )
        problems = validate_report(
            report,
            observation_ids={
                o.observation_id for f in run.findings.values() for o in f.observations
            },
            finding_agents=set(run.findings),
        )
        if problems:  # pragma: no cover - would be a builder bug
            raise RuntimeError("fallback report invalid: " + "; ".join(problems))
        return report, render_markdown(report), True

    def _finish(
        self, run: _Run, report: dict[str, Any], *, markdown: str | None = None
    ) -> IncidentResult:
        md = markdown if markdown is not None else render_markdown(report)
        self.store.append_report(run.incident, report, md, at=self.clock.now())
        return IncidentResult(
            incident_id=run.incident,
            final_state=self._state.get(run.incident) or "UNKNOWN",
            report=report,
            markdown=md,
            decision=run.decision,
            findings=dict(run.findings),
            missing_agents=list(run.missing or []),
            issues=run.issues,
        )


def _submit(
    pool: cf.ThreadPoolExecutor | None, bus: MessageBus, sent: ParsedMessage
) -> cf.Future[Any]:
    assert pool is not None
    return pool.submit(bus.call_handler, sent)

"""Shared behaviour of the specialist agents (doc 03 §1 checklist).

A specialist receives a ``task_request`` (goal, scope, window, budget), investigates
through its own :class:`~netcoop.tools.toolbox.ToolSession`, and replies with an
independent ``finding``. Its investigation is *bounded and rule-driven* (doc 03 §1 honest
limitation), but adaptive:

1. **screen** its metrics for the whole scope (one call);
2. **check coverage** to learn why anything is missing;
3. **deep-dive** each anomalous entity (most severe first) over the *whole* bundle — a
   widened window — to classify the pattern and find the onset, while budget remains.

So a quiet scenario takes two calls and a faulty one takes more (T-AGT-BEHAV-03). Missing
or unreadable data is reported as not assessable, never as normal (T-AGT-BEHAV-05).
"""

from __future__ import annotations

import itertools
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from functools import partial
from typing import Any, ClassVar

from netcoop.config.fields import FieldDictionary, load_field_dictionary
from netcoop.core.blocks import (
    EvidenceRef,
    Hypothesis,
    Limitation,
    NotAssessableItem,
    Observation,
    SelfAssessment,
    TimeWindow,
)
from netcoop.core.bus import MessageBus
from netcoop.core.messages import (
    AgentError,
    ClarificationRequest,
    ClarificationResponse,
    ConflictReport,
    ConflictResponse,
    Envelope,
    Finding,
    ParsedMessage,
    TaskRequest,
)
from netcoop.core.vocab import AgentId, CauseType, Severity
from netcoop.diagnosis.params import DiagnosisParams
from netcoop.diagnosis.severity import grade, rank, worst
from netcoop.ingestion.models import MetricState
from netcoop.tools.toolbox import Sample, ToolBox, ToolError, ToolSession

ToolBoxProvider = Callable[[str], ToolBox]
CLARIFICATION_BUDGET = 3
_STRENGTH = {"normal": 0.0, "elevated": 0.5, "critical": 1.0, "unknown": 0.0}


@dataclass
class Investigation:
    """Working state of one task (local to the call; agents keep no state between tasks)."""

    session: ToolSession
    scope: list[str]
    window: TimeWindow
    id_prefix: str
    samples: dict[tuple[str, str], list[Sample]] = field(default_factory=dict)
    coverage: dict[tuple[str, str], MetricState] = field(default_factory=dict)
    deep: dict[str, list[Sample]] = field(default_factory=dict)
    limitations: list[Limitation] = field(default_factory=list)
    counter: int = 0

    def next_id(self) -> str:
        self.counter += 1
        return f"{self.id_prefix}-{self.counter:03d}"


class SpecialistAgent:
    agent_id: ClassVar[AgentId]
    short: ClassVar[str]
    goal: ClassVar[str]
    items: ClassVar[tuple[str, ...]]

    def __init__(
        self,
        bus: MessageBus,
        toolboxes: ToolBoxProvider,
        params: DiagnosisParams,
        fields: FieldDictionary | None = None,
    ) -> None:
        self.bus = bus
        self.toolboxes = toolboxes
        self.params = params
        self.fields = fields or load_field_dictionary()

    # ------------------------------------------------------------------ message entry
    def handle(self, msg: ParsedMessage) -> Envelope:
        try:
            if isinstance(msg.payload, TaskRequest):
                finding = self.investigate(msg.payload, msg).model_copy(
                    update={"task_id": msg.payload.task_id}
                )
                return self.bus.reply(
                    msg,
                    message_type="finding",
                    payload=finding,
                    status="partial" if finding.self_assessment.assessed_fraction < 1 else "ok",
                )
            if isinstance(msg.payload, ClarificationRequest):
                return self.bus.reply(
                    msg,
                    message_type="clarification_response",
                    payload=self.clarify(msg.payload, msg).model_copy(
                        update={
                            "clarification_id": msg.payload.clarification_id,
                            "source": self.agent_id,
                        }
                    ),
                )
            if isinstance(msg.payload, ConflictReport):
                return self.bus.reply(
                    msg,
                    message_type="conflict_response",
                    payload=self.respond_to_conflict(msg.payload, msg),
                )
            raise ValueError(f"{self.agent_id} cannot handle {msg.envelope.message_type}")
        except Exception as exc:  # an agent never crashes the bus; it reports
            return self.bus.reply(
                msg,
                message_type="agent_error",
                payload=AgentError(
                    code="AGENT_FAILED", message=f"{type(exc).__name__}: {exc}", recoverable=False
                ),
                status="error",
            )

    def _toolbox(self, msg: ParsedMessage) -> ToolBox:
        return self.toolboxes(msg.envelope.incident_id or "")

    def _prefix(self, msg: ParsedMessage) -> str:
        return f"OBS-{self.short}-{msg.envelope.message_id.split('-')[-1]}"

    # ------------------------------------------------------------------ investigation
    def investigate(self, task: TaskRequest, msg: ParsedMessage) -> Finding:
        inv = Investigation(
            session=self._toolbox(msg).session(self.agent_id, task.tool_budget),
            scope=sorted(set(task.scope_entities)),
            window=task.window,
            id_prefix=self._prefix(msg),
        )
        self.screen(inv)
        self.check_coverage(inv)
        self.deep_dive(inv)
        observations, not_assessable = self.build_observations(inv)
        facts = self.extra_facts(inv, observations, not_assessable)
        hypotheses = self.local_hypotheses(observations, inv)
        if inv.session.exhausted and not any(
            lim.code == "TOOL_BUDGET_EXHAUSTED" for lim in inv.limitations
        ):
            inv.limitations.append(
                Limitation(
                    code="TOOL_BUDGET_EXHAUSTED",
                    text=f"{self.agent_id} used all {inv.session.budget} tool calls; "
                    "the investigation may be incomplete.",
                )
            )
        return Finding(
            observations=observations,
            hypotheses=hypotheses,
            not_assessable=not_assessable,
            limitations=inv.limitations,
            tool_calls=inv.session.records,
            self_assessment=SelfAssessment(
                assessed_fraction=round(self.assessed_fraction(inv, observations, facts), 4),
                budget_exhausted=inv.session.exhausted,
            ),
            facts=facts,
        )

    def _try(self, inv: Investigation, fn: Callable[[], Any]) -> Any:
        try:
            return fn()
        except ToolError as exc:
            inv.limitations.append(Limitation(code="TOOL_BUDGET_EXHAUSTED", text=str(exc)))
            return None

    def screen(self, inv: Investigation) -> None:
        samples = self._try(inv, lambda: inv.session.telemetry_query(inv.scope, list(self.items)))
        if samples is None:
            return
        grouped: dict[tuple[str, str], list[Sample]] = defaultdict(list)
        for s in samples:
            if inv.window.start <= s.timestamp <= inv.window.end:
                grouped[(s.entity, s.metric)].append(s)
        inv.samples = dict(grouped)

    def check_coverage(self, inv: Investigation) -> None:
        if not inv.session.can_call("coverage_query"):
            return
        cov = self._try(inv, lambda: inv.session.coverage_query(inv.scope, list(self.items)))
        inv.coverage = cov or {}

    def anomalous_entities(self, inv: Investigation) -> list[str]:
        worst_by_entity: dict[str, int] = {}
        for (e, i), ss in inv.samples.items():
            sev = worst([grade(i, s.value, self.params) for s in ss])
            worst_by_entity[e] = max(worst_by_entity.get(e, -1), rank(sev))
        return sorted(
            (e for e, r in worst_by_entity.items() if r >= rank("elevated")),
            key=lambda e: (-worst_by_entity[e], e),
        )

    def deep_dive(self, inv: Investigation) -> None:
        for entity in self.anomalous_entities(inv):
            if not inv.session.can_call("telemetry_query"):
                inv.limitations.append(
                    Limitation(
                        code="TOOL_BUDGET_EXHAUSTED",
                        text=f"Budget exhausted before deep-dive on {entity}.",
                    )
                )
                break
            got = self._try(inv, partial(inv.session.telemetry_query, [entity], list(self.items)))
            if got is not None:
                inv.deep[entity] = got

    # ------------------------------------------------------------------ observations
    def _unit(self, item: str) -> str:
        spec = self.fields.fields.get(item)
        return spec.unit if spec else "none"

    def _category(self, item: str) -> str:
        spec = self.fields.fields.get(item)
        return spec.category if spec else item

    def _pattern(self, item: str, history: list[Sample]) -> list[str]:
        if len(history) < 2:
            return ["pattern:single-sample"]
        sevs = [grade(item, s.value, self.params) for s in history]
        abnormal = [rank(s) >= rank("elevated") for s in sevs]
        flags: list[str] = []
        onset = next((h.timestamp for h, a in zip(history, abnormal, strict=True) if a), None)
        if all(abnormal):
            flags.append("pattern:sustained")
        elif sum(abnormal) == 1:
            flags.append("pattern:spike")
        elif abnormal[-1] and _rising(history):
            flags.append("pattern:rising")
        else:
            flags.append("pattern:intermittent")
        if onset is not None:
            flags.append(f"onset:{onset.isoformat()}")
        return flags

    def _make_obs(
        self,
        inv: Investigation,
        entity: str,
        item: str,
        samples: list[Sample],
        extra_flags: list[str],
    ) -> Observation:
        pick = max(
            samples, key=lambda s: (rank(grade(item, s.value, self.params)), _magnitude(s.value))
        )
        sev: Severity = grade(item, pick.value, self.params)
        state = inv.coverage.get((entity, item))
        caveat = state is not None and state.assessability == "assessed_with_caveat"
        flags = sorted({f for s in samples for f in s.flags} | set(extra_flags))
        if caveat and state is not None and state.reason:
            flags.append(state.reason)
        return Observation(
            observation_id=inv.next_id(),
            entity=entity,
            metric=item,
            metric_category=self._category(item),
            value=pick.value,
            unit=self._unit(item),
            window=TimeWindow(
                start=min(s.timestamp for s in samples), end=max(s.timestamp for s in samples)
            ),
            severity=sev,
            assessability="assessed_with_caveat" if caveat else "assessed",
            quality_flags=flags,
            source_ref=sorted({s.record_id for s in samples}),
            agent=self.agent_id,
        )

    def build_observations(
        self, inv: Investigation
    ) -> tuple[list[Observation], list[NotAssessableItem]]:
        observations: list[Observation] = []
        not_assessable: list[NotAssessableItem] = []
        for entity in inv.scope:
            for item in self.items:
                samples = inv.samples.get((entity, item), [])
                if not samples:
                    state = inv.coverage.get((entity, item))
                    reason = state.reason if state and state.reason else "MISSING"
                    detail = state.detail if state else "not observed (coverage unknown)"
                    not_assessable.append(
                        NotAssessableItem(entity=entity, metric=item, reason=reason, detail=detail)
                    )
                    if item == "status":  # doc 03 §2.2: "status unknown" is an observation
                        observations.append(
                            Observation(
                                observation_id=inv.next_id(),
                                entity=entity,
                                metric=item,
                                metric_category=self._category(item),
                                value=None,
                                unit="none",
                                window=inv.window,
                                severity="unknown",
                                assessability="not_assessable",
                                not_assessable_reason=reason,
                                quality_flags=[f"status unknown ({reason})"],
                                agent=self.agent_id,
                            )
                        )
                    continue
                history = [s for s in inv.deep.get(entity, []) if s.metric == item]
                extra = self._pattern(item, history) if history else []
                # Conflicting records (same entity+time, different values) become separate
                # observations so the correlation agent's conflict rules can see them.
                conflicted = [s for s in samples if "CONFLICT" in s.flags]
                groups = _conflict_groups(item, conflicted, self.params)
                if len(groups) > 1:
                    plain = [s for s in samples if "CONFLICT" not in s.flags]
                    for g in groups:
                        observations.append(
                            self._make_obs(inv, entity, item, [*plain, *g], [*extra, "conflict"])
                        )
                else:
                    observations.append(self._make_obs(inv, entity, item, samples, extra))
        return observations, not_assessable

    # ------------------------------------------------------------------ extension points
    def assessed_fraction(
        self, inv: Investigation, observations: list[Observation], facts: dict[str, Any]
    ) -> float:
        total = max(1, len(inv.scope) * len(self.items))
        assessed = sum(1 for o in observations if o.assessability != "not_assessable")
        return min(1.0, assessed / total)

    def extra_facts(
        self,
        inv: Investigation,
        observations: list[Observation],
        not_assessable: list[NotAssessableItem],
    ) -> dict[str, Any]:
        return {}

    def local_hypotheses(
        self, observations: list[Observation], inv: Investigation
    ) -> list[Hypothesis]:
        return []

    # ------------------------------------------------------------------ conflicts (1.2)
    def respond_to_conflict(self, report: ConflictReport, msg: ParsedMessage) -> ConflictResponse:
        """Re-check what the report asks and state a stance derived from the result:
        cannot_assess (no answer), withdraw (the data is not usable), maintain (the readings
        still disagree), revise (one consistent reading, sent as new evidence)."""
        recheck = {k: v for k, v in report.recheck.items() if k != "question_type"}
        answer = self.clarify(
            ClarificationRequest(
                question_type=report.recheck.get("question_type", "recheck_metric"),
                target=self.agent_id,
                parameters=recheck,
                reason="conflict",
                round=report.round,
            ),
            msg,
        )
        obs = answer.observations
        if not answer.answered or not obs:
            stance, note = "cannot_assess", answer.reason or "no data to re-check"
        elif all(o.assessability == "not_assessable" for o in obs):
            stance, note = "withdraw", "the re-checked data is not usable"
        elif len({o.severity for o in obs}) > 1:
            stance, note = "maintain", "the re-check still shows disagreeing readings"
        else:
            stance, note = "revise", f"re-checked reading: {obs[0].severity}"
        return ConflictResponse(
            conflict_id=report.conflict_id,
            stance=stance,
            evidence=[
                EvidenceRef(
                    evidence_type="observation", evidence_id=o.observation_id, stance="supports"
                )
                for o in obs
            ],
            observations=obs,
            note=note,
            source=self.agent_id,
            clarification_id=report.clarification_id,
        )

    # ------------------------------------------------------------------ clarification
    def clarify(self, req: ClarificationRequest, msg: ParsedMessage) -> ClarificationResponse:
        p = req.parameters
        items: tuple[str, ...]
        if req.question_type == "recheck_metric" and p.get("metric") in self.items:
            entities, items = [str(p.get("entity"))], (str(p["metric"]),)
        elif req.question_type in ("assess_additional_entities", "widen_time_window"):
            raw = p.get("entities") or ([p["entity"]] if "entity" in p else [])
            entities, items = sorted(str(e) for e in raw), self.items
        else:
            return ClarificationResponse(
                answered=False,
                reason=f"{self.agent_id} cannot answer {req.question_type} "
                f"with parameters {sorted(p)}",
            )
        if not entities:
            return ClarificationResponse(answered=False, reason="no entities given")
        session = self._toolbox(msg).session(self.agent_id, CLARIFICATION_BUDGET)
        bundle_window = self._toolbox(msg).window
        inv = Investigation(
            session=session, scope=entities, window=bundle_window, id_prefix=self._prefix(msg)
        )
        samples = self._try(inv, lambda: session.telemetry_query(entities, list(items)))
        if samples is None:
            return ClarificationResponse(answered=False, reason="tool budget exhausted")
        grouped: dict[tuple[str, str], list[Sample]] = defaultdict(list)
        for s in samples:
            grouped[(s.entity, s.metric)].append(s)
        obs = [
            self._make_obs(inv, e, i, ss, [f"clarification:{req.question_type}"])
            for (e, i), ss in sorted(grouped.items())
        ]
        if not obs:
            return ClarificationResponse(
                answered=False, reason=f"no data for {entities} / {list(items)}"
            )
        return ClarificationResponse(answered=True, observations=obs)

    # ------------------------------------------------------------------ helpers for rules
    @staticmethod
    def by_entity(observations: list[Observation]) -> dict[str, dict[str, Observation]]:
        out: dict[str, dict[str, Observation]] = defaultdict(dict)
        for o in observations:
            if o.assessability == "not_assessable":
                continue
            prev = out[o.entity].get(o.metric)
            if prev is None or rank(o.severity) > rank(prev.severity):
                out[o.entity][o.metric] = o
        return out

    @staticmethod
    def hypothesis(
        prefix: str,
        n: int,
        cause: CauseType,
        entity: str,
        support: list[Observation],
        rationale: str,
        missing: list[str] | None = None,
    ) -> Hypothesis:
        score = sum(_STRENGTH[o.severity] for o in support) / max(1, len(support))
        return Hypothesis(
            hypothesis_id=f"HYP-{prefix}-{n:03d}",
            cause_type=cause,
            entities=[entity],
            supporting_observation_ids=[o.observation_id for o in support],
            missing_expected_evidence=missing or [],
            local_score=round(score, 4),
            rationale_code=rationale,
        )


def is_abnormal(o: Observation | None) -> bool:
    return o is not None and o.severity in ("elevated", "critical")


def is_normal(o: Observation | None) -> bool:
    return o is not None and o.severity == "normal"


def _magnitude(value: float | str) -> float:
    return float(value) if isinstance(value, int | float) else 0.0


def _rising(history: list[Sample]) -> bool:
    values = [_magnitude(s.value) for s in history]
    return all(b >= a for a, b in itertools.pairwise(values)) and values[-1] > values[0]


def _conflict_groups(
    item: str, conflicted: list[Sample], params: DiagnosisParams
) -> list[list[Sample]]:
    by_time: dict[datetime, list[Sample]] = defaultdict(list)
    for s in conflicted:
        by_time[s.timestamp].append(s)
    groups: dict[str, list[Sample]] = defaultdict(list)
    for ss in by_time.values():
        if len({grade(item, s.value, params) for s in ss}) > 1:
            for s in ss:
                groups[grade(item, s.value, params)].append(s)
    return [groups[k] for k in sorted(groups)]

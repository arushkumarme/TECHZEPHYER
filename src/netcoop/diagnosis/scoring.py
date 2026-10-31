"""Hypothesis scoring and the decision gate (doc 08 §4), deterministic.

Per hypothesis h (evaluated per entity, then merged per cause):

    S_h  = Σ w_i·e_i / Σ w_i          all applicable signature items, incl. not-assessable
    C_h  = min(1, Σ v_j·c_j)          contradicting evidence
    U_h  = share of the entity's abnormal items that h's signature does not explain  (ID-11)
    B_h  = β if ≥ 2 independent agents support h
    base = clamp(S_h - lambda*C_h - mu*U_h + B_h + B_comm, 0, 1)
    score = min(base, ceiling)        ceiling from data quality, topology, missing agents

The margin between the top two causes is computed on ``base`` so the data-quality
ceiling cannot manufacture a tie (ID-12). Community evidence (B_comm <= gamma_max) is
excluded from ranking and from every gate condition, so complaints can never change the
decision - only the displayed confidence (doc 08 §6).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime

from netcoop.core.blocks import Limitation, ScoredHypothesis
from netcoop.core.messages import Decision
from netcoop.core.vocab import ConfidenceCategory, DecisionKind
from netcoop.diagnosis.catalog import (
    CATALOG,
    DERIVED_ITEMS,
    REQUIREMENT_TEXT,
    CauseSpec,
    SignatureItem,
)
from netcoop.diagnosis.evidence import EvidenceView
from netcoop.diagnosis.params import DiagnosisParams

_DATA_PROBLEMS = {"UNMAPPED_FIELD", "UNIT_AMBIGUOUS", "MALFORMED", "IMPLAUSIBLE"}
_ENTITY_ITEMS_EXCLUDED = {"probe_dns", "probe_dhcp"}


@dataclass(frozen=True)
class CommunityContext:
    """An unverified community candidate mapped to topology entities (doc 08 §6)."""

    candidate_id: str
    entities: tuple[str, ...]
    start: datetime
    end: datetime


@dataclass
class DiagnosisContext:
    q: float
    topology_available: bool
    available: dict[str, bool]
    missing_agents: list[str] = field(default_factory=list)
    window_start: datetime | None = None
    window_end: datetime | None = None
    community: list[CommunityContext] = field(default_factory=list)


@dataclass
class _ItemEval:
    e: float
    applicable: bool
    assessable: bool
    observation_ids: tuple[str, ...] = ()
    agents: tuple[str, ...] = ()


@dataclass
class _EntityScore:
    entity: str
    support: float
    contradiction: float
    unexplained: float
    sources: set[str]
    matched: list[str]
    symptomatic: bool
    missing: list[str]
    supporting_ids: list[str]
    contradicting_ids: list[str]


# ------------------------------------------------------------------------- item evaluation


def _entity_items(view: EvidenceView) -> list[str]:
    return [i for i in view.items_per_entity if i not in _ENTITY_ITEMS_EXCLUDED]


def _plain(view: EvidenceView, entity: str, item: str, mode: str, e_mid: float) -> _ItemEval:
    ev = view.get(entity, item)
    if ev is None:
        return _ItemEval(0.0, applicable=True, assessable=False)
    e = ev.strength(mode, e_mid)
    return _ItemEval(e, True, True, ev.observation_ids, ev.agents)


def _congestion_support(view: EvidenceView, entity: str, p: DiagnosisParams) -> _ItemEval:
    spec = CATALOG["link_congestion"]
    num = den = 0.0
    ids: list[str] = []
    agents: set[str] = set()
    for s in spec.signature:
        w = p.weights[s.cls]
        ev = _plain(view, entity, s.item, s.mode, p.scoring.e_mid)
        num += w * ev.e
        den += w
        if ev.e > 0:
            ids.extend(ev.observation_ids)
            agents.update(ev.agents)
    return _ItemEval(num / den if den else 0.0, True, True, tuple(ids), tuple(sorted(agents)))


def _evaluate(view: EvidenceView, entity: str, s: SignatureItem, p: DiagnosisParams) -> _ItemEval:
    if not s.item.startswith("@"):
        return _plain(view, entity, s.item, s.mode, p.scoring.e_mid)
    facts = view.facts
    conn = (DERIVED_ITEMS[s.item],)
    if s.item == "@upstream_congestion":
        paths = facts.get("paths", {}) if facts.get("topology_available") else {}
        path = paths.get(entity)
        if not path:
            return _ItemEval(0.0, True, False)
        best = _ItemEval(0.0, True, True, (), conn)
        for up in path[1:]:
            cand = _congestion_support(view, up, p)
            if cand.e > best.e:
                best = _ItemEval(
                    cand.e, True, True, cand.observation_ids, tuple(sorted({*cand.agents, *conn}))
                )
        return best
    if s.item == "@downstream_affected":
        if not facts.get("topology_available"):
            return _ItemEval(0.0, True, False)
        isolated = facts.get("what_if", {}).get(entity, {}).get("isolated", [])
        if not isolated:
            return _ItemEval(0.0, applicable=False, assessable=True)
        observed = [d for d in isolated if d in view.entities]
        if not observed:
            return _ItemEval(0.0, True, False)
        hit = [
            d
            for d in observed
            if any(
                (ev := view.get(d, i)) is not None and ev.abnormal
                for i in ("status", "latency_ms", "packet_loss_pct")
            )
        ]
        return _ItemEval(len(hit) / len(observed), True, True, (), conn)
    if s.item in ("@probe_failures", "@probe_success"):
        probes = [ev for (e, i), ev in view.items.items() if e == entity and i.startswith("probe_")]
        if not probes:
            return _ItemEval(0.0, True, False)
        failing = sum(1 for ev in probes if ev.abnormal)
        share = failing / len(probes) if s.item == "@probe_failures" else 1 - failing / len(probes)
        ids = tuple(i for ev in probes for i in ev.observation_ids)
        return _ItemEval(share, True, True, ids, conn)
    if s.item == "@network_normal":
        evs = [
            ev
            for i in _entity_items(view)
            if i != "status" and (ev := view.get(entity, i)) is not None
        ]
        if not evs:
            return _ItemEval(0.0, True, False)
        normal = [ev for ev in evs if ev.strength("normal", 0) == 1.0]
        return _ItemEval(
            len(normal) / len(evs),
            True,
            True,
            tuple(i for ev in normal for i in ev.observation_ids),
            tuple(sorted({a for ev in normal for a in ev.agents})),
        )
    raise KeyError(s.item)


def _score_entity(
    view: EvidenceView, entity: str, spec: CauseSpec, p: DiagnosisParams
) -> _EntityScore:
    num = den = 0.0
    sources: set[str] = set()
    matched: list[str] = []
    missing: list[str] = []
    supporting: list[str] = []
    symptomatic = False
    for s in spec.signature:
        ev = _evaluate(view, entity, s, p)
        if not ev.applicable:
            continue
        w = p.weights[s.cls]
        den += w
        num += w * ev.e
        if not ev.assessable:
            missing.append(f"{entity}:{s.item}")
        elif ev.e > 0:
            matched.append(s.item)
            symptomatic = symptomatic or s.mode == "abnormal"
            sources.update(ev.agents)
            supporting.extend(ev.observation_ids)
    contradiction = 0.0
    contradicting: list[str] = []
    for c in spec.contradicting:
        v = p.contradiction_weights[c.cls]
        if c.item.startswith("@"):
            ev = _evaluate(view, entity, SignatureItem(c.item, "weak"), p)
            strength, ids = (ev.e if ev.assessable else 0.0), ev.observation_ids
        else:
            item_ev = view.get(entity, c.item)
            if item_ev is None:
                continue
            ids = item_ev.observation_ids
            if c.when == "normal":
                strength = item_ev.strength("normal", 0)
            elif c.when == "critical":
                strength = 1.0 if all(x == "critical" for x in item_ev.severities) else 0.0
            else:
                strength = item_ev.strength("abnormal", p.scoring.e_mid)
        if strength > 0:
            contradiction += v * strength
            contradicting.extend(ids)
    explained = {s.item for s in spec.signature if s.mode == "abnormal"}
    abnormal_items = [
        i for i in _entity_items(view) if (got := view.get(entity, i)) is not None and got.abnormal
    ]
    unexplained = (
        sum(1 for i in abnormal_items if i not in explained) / len(abnormal_items)
        if abnormal_items
        else 0.0
    )
    return _EntityScore(
        entity=entity,
        support=num / den if den else 0.0,
        contradiction=min(1.0, contradiction),
        unexplained=unexplained,
        sources=sources,
        matched=matched,
        symptomatic=symptomatic,
        missing=missing,
        supporting_ids=supporting,
        contradicting_ids=contradicting,
    )


# ------------------------------------------------------------------------- scoring


def _ceiling(ctx: DiagnosisContext, p: DiagnosisParams, cause: str) -> float:
    if cause == "telemetry_unreliable":
        return 1.0
    cap = p.ceiling.cap(ctx.q)
    if not ctx.topology_available:
        cap -= p.ceiling.missing_topology_penalty
    cap -= p.ceiling.missing_agent_penalty * len(ctx.missing_agents)
    return max(0.0, round(cap, 6))


def _community_bonus(entities: list[str], ctx: DiagnosisContext, p: DiagnosisParams) -> float:
    if not ctx.community or not entities:
        return 0.0
    for c in ctx.community:
        overlaps_time = (
            ctx.window_start is None
            or ctx.window_end is None
            or (c.start <= ctx.window_end and ctx.window_start <= c.end)
        )
        if overlaps_time and set(c.entities) & set(entities):
            return p.scoring.gamma_max
    return 0.0


def _clamp(x: float) -> float:
    return max(0.0, min(1.0, x))


def _finish(
    cause: str,
    entities: list[str],
    support: float,
    contradiction: float,
    unexplained: float,
    sources: set[str],
    matched: list[str],
    missing: list[str],
    supporting_ids: list[str],
    contradicting_ids: list[str],
    ctx: DiagnosisContext,
    p: DiagnosisParams,
) -> ScoredHypothesis:
    s = p.scoring
    corroboration = s.beta if len(sources) >= 2 else 0.0
    raw = support - s.lambda_ * contradiction - s.mu * unexplained + corroboration
    telemetry_base = round(_clamp(raw), 4)
    base = round(_clamp(raw + _community_bonus(entities, ctx, p)), 4)
    ceiling = _ceiling(ctx, p, cause)
    return ScoredHypothesis(
        cause_type=cause,
        entities=sorted(entities),
        score=round(min(base, ceiling), 4),
        support=round(support, 4),
        contradiction=round(contradiction, 4),
        corroboration=corroboration,
        # The increment actually applied (clamping can absorb part of the bonus), so
        # base - community_bonus is exactly the telemetry-only base.
        community_bonus=round(base - telemetry_base, 4),
        unexplained=round(unexplained, 4),
        base=base,
        ceiling=ceiling,
        supporting_observation_ids=sorted(set(supporting_ids)),
        contradicting_observation_ids=sorted(set(contradicting_ids)),
        missing_expected_evidence=sorted(set(missing)),
        supporting_sources=sorted(sources),
        matched_signature_items=sorted(set(matched)),
        diagnosable=ctx.available.get(cause, True),
    )


def _score_normal(
    view: EvidenceView, ctx: DiagnosisContext, p: DiagnosisParams
) -> ScoredHypothesis:
    items = _entity_items(view)
    normal_pairs = 0
    ids: list[str] = []
    contra_ids: list[str] = []
    sources: set[str] = set()
    matched: set[str] = set()
    contradiction = 0.0
    for e in view.entities:
        for i in items:
            ev = view.get(e, i)
            if ev is None:
                continue
            if ev.strength("normal", 0) == 1.0:
                normal_pairs += 1
                ids.extend(ev.observation_ids)
                sources.update(ev.agents)
                matched.add(i)
            elif any(x in ("elevated", "critical") for x in ev.severities):
                # Includes unresolved conflicts where only SOME readings are abnormal: a
                # conflicting critical reading means "within expected ranges" is unproven.
                contradiction += 1.0 if "critical" in ev.severities else 0.5
                contra_ids.extend(ev.observation_ids)
    for (_, item), ev in view.items.items():
        if item.startswith("probe_") and ev.abnormal:
            contradiction += 1.0
            contra_ids.extend(ev.observation_ids)
    total = max(1, len(view.entities) * len(items))
    missing = [f"{e}:{i}" for (e, i) in view.not_assessable if i in items]
    return _finish(
        "normal_operation",
        [],
        normal_pairs / total,
        min(1.0, contradiction),
        0.0,
        sources,
        sorted(matched),
        missing,
        ids,
        contra_ids,
        ctx,
        p,
    )


def _score_unreliable(
    view: EvidenceView, ctx: DiagnosisContext, p: DiagnosisParams, problem_agents: set[str]
) -> ScoredHypothesis:
    items = _entity_items(view)
    total = max(1, len(view.entities) * len(items))
    problems = [k for k, r in view.not_assessable.items() if r in _DATA_PROBLEMS and k[1] in items]
    stale = [k for k, ev in view.items.items() if ev.caveat and k[1] in items]
    share = (len(problems) + 0.5 * len(stale)) / total
    support = min(1.0, 2 * share)
    matched = sorted({i for _, i in problems} | ({"freshness"} if stale else set()))
    return _finish(
        "telemetry_unreliable",
        [],
        support,
        0.0,
        0.0,
        problem_agents if problems else set(),
        matched,
        [],
        [],
        [],
        ctx,
        p,
    )


def score_hypotheses(
    view: EvidenceView,
    ctx: DiagnosisContext,
    p: DiagnosisParams,
    *,
    problem_agents: set[str] | None = None,
) -> list[ScoredHypothesis]:
    """Score every catalog cause; return them ranked (deterministic order)."""
    out = [
        _score_normal(view, ctx, p),
        _score_unreliable(view, ctx, p, problem_agents or set()),
    ]
    probe_entities = sorted({e for (e, i) in view.items if i.startswith("probe_")})
    for cause, spec in CATALOG.items():
        if cause in ("normal_operation", "telemetry_unreliable"):
            continue
        if not ctx.available.get(cause, True):
            out.append(
                _finish(
                    cause,
                    [],
                    0.0,
                    0.0,
                    0.0,
                    set(),
                    [],
                    [f"*:{r}" for r in spec.requires],
                    [],
                    [],
                    ctx,
                    p,
                )
            )
            continue
        candidates = probe_entities if cause == "dns_dhcp_failure" else view.entities
        per_entity = [_score_entity(view, e, spec, p) for e in candidates]
        finished = [
            (
                es,
                _finish(
                    cause,
                    [es.entity],
                    es.support,
                    es.contradiction,
                    es.unexplained,
                    es.sources,
                    es.matched,
                    es.missing,
                    es.supporting_ids,
                    es.contradicting_ids,
                    ctx,
                    p,
                ),
            )
            for es in per_entity
            if es.symptomatic
        ]
        if not finished:
            out.append(_finish(cause, [], 0.0, 0.0, 0.0, set(), [], [], [], [], ctx, p))
            continue
        finished.sort(key=lambda t: (-t[1].base, t[1].entities))
        # Group devices whose scores are within delta of a group leader; every group is
        # its own hypothesis, so a weaker same-cause problem elsewhere is never hidden.
        remaining = [h for _, h in finished]
        while remaining:
            leader = remaining[0]
            group = [h for h in remaining if leader.base - h.base < p.gate.delta]
            remaining = [h for h in remaining if h not in group]
            out.append(_merge(leader, group))
    return sorted(out, key=_rank_key)


def _merge(leader: ScoredHypothesis, group: list[ScoredHypothesis]) -> ScoredHypothesis:
    if len(group) == 1:
        return leader
    return leader.model_copy(
        update={
            "entities": sorted({e for h in group for e in h.entities}),
            "supporting_observation_ids": sorted(
                {i for h in group for i in h.supporting_observation_ids}
            ),
            "contradicting_observation_ids": sorted(
                {i for h in group for i in h.contradicting_observation_ids}
            ),
            "missing_expected_evidence": sorted(
                {i for h in group for i in h.missing_expected_evidence}
            ),
        }
    )


def telemetry_score(h: ScoredHypothesis) -> float:
    """Score without the community term — used for ranking and the gate (doc 08 §6)."""
    return round(min(h.base - h.community_bonus, h.ceiling), 4)


def _rank_key(h: ScoredHypothesis) -> tuple[bool, float, float, str]:
    return (not h.diagnosable, -telemetry_score(h), -(h.base - h.community_bonus), h.cause_type)


# ------------------------------------------------------------------------- decision gate


def _category(score: float, p: DiagnosisParams) -> ConfidenceCategory:
    if score >= p.categories.t_high:
        return "high"
    if score >= p.categories.t_med:
        return "medium"
    return "low"


def decide(
    ranked: list[ScoredHypothesis],
    view: EvidenceView,
    ctx: DiagnosisContext,
    p: DiagnosisParams,
    *,
    coverage: float,
) -> Decision:
    g = p.gate
    candidates = [h for h in ranked if h.diagnosable]
    top = candidates[0]
    second = candidates[1] if len(candidates) > 1 else None
    # Community evidence may raise displayed confidence but never the gate (doc 08 §6):
    # score and margin conditions use values without the community term.
    margin = (
        None
        if second is None
        else round((top.base - top.community_bonus) - (second.base - second.community_bonus), 4)
    )
    community_free = set(top.supporting_sources) - {"community_module"}
    key_items = {s.item for s in CATALOG[top.cause_type].signature if s.cls == "key"}
    checks = {
        "score_at_least_tau": telemetry_score(top) >= g.tau_diag,
        "key_evidence_present": not key_items or bool(key_items & set(top.matched_signature_items)),
        "min_signature_items": len(top.matched_signature_items) >= g.n_min,
        "min_independent_sources": len(community_free) >= g.s_min,
        "margin_at_least_delta": margin is None or margin >= g.delta,
        "not_telemetry_unreliable": top.cause_type != "telemetry_unreliable",
        "diagnosable": top.diagnosable,
    }
    kind: DecisionKind
    if top.cause_type == "normal_operation":
        checks["coverage_at_least_min"] = coverage >= g.coverage_min
        # PDF p4: normal = "measurements remain within expected ranges". Any assessed
        # abnormal measurement means an anomaly exists, so "no fault" cannot be claimed.
        checks["no_abnormal_measurements"] = top.contradiction == 0
        ok = all(
            checks[k]
            for k in (
                "score_at_least_tau",
                "margin_at_least_delta",
                "coverage_at_least_min",
                "min_independent_sources",
                "no_abnormal_measurements",
            )
        )
        kind = "no_fault_detected" if ok else "insufficient_evidence"
    else:
        kind = "diagnosed" if all(checks.values()) else "insufficient_evidence"

    limitations: list[Limitation] = []
    for h in ranked:
        if not h.diagnosable:
            spec = CATALOG[h.cause_type]
            limitations.append(
                Limitation(
                    code="CAUSE_NOT_ASSESSABLE",
                    text=f"{spec.label} cannot be assessed with the supplied data "
                    f"(missing: {', '.join(REQUIREMENT_TEXT.get(r, r) for r in spec.requires)}).",
                )
            )
    for agent in ctx.missing_agents:
        limitations.append(
            Limitation(
                code="AGENT_MISSING", text=f"No finding from {agent}; its evidence is absent."
            )
        )
    if not ctx.topology_available:
        limitations.append(
            Limitation(
                code="TOPOLOGY_MISSING",
                text="No topology available: affected scope and blast radius are unknown.",
            )
        )
    for c in view.conflicts:
        if c.rule == "unresolved":
            limitations.append(Limitation(code="CONFLICT_UNRESOLVED", text=c.description))
    if kind == "insufficient_evidence":
        failed = sorted(k for k, v in checks.items() if not v)
        limitations.append(
            Limitation(
                code="GATE_NOT_MET",
                text="Evidence insufficient for a single probable cause "
                f"(failed: {', '.join(failed)}).",
            )
        )

    confidence = top.score if kind != "insufficient_evidence" else min(top.score, g.c_insuff_cap)
    category: ConfidenceCategory = (
        "insufficient" if kind == "insufficient_evidence" else _category(top.score, p)
    )
    return Decision(
        decision=kind,
        ranked=ranked,
        margin=margin,
        gate_checks=checks,
        confidence=round(confidence, 4),
        confidence_category=category,
        conflicts=view.conflicts,
        limitations=limitations,
        affected_entities=[] if top.cause_type == "normal_operation" else top.entities,
    )

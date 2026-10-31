"""Evidence view over agent findings, with conflict resolution (doc 08 §5).

Conflicts between observations of the same entity-item are resolved in order:

1. **evidence class** — direct measurement > derived > user report;
2. **freshness** — newer beats older when windows end more than the tolerance apart;
3. (topology consistency acts through the scorer's ``@downstream_affected`` item);
4. **unresolved** — both kept; the scorer uses the *weaker* evidence (conservative), and
   the conflict is recorded as a limitation. No observation is dropped silently: every
   disregarded one is listed with its reason.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any

from netcoop.core.blocks import ConflictRecord, NotAssessableItem, Observation
from netcoop.core.vocab import Severity
from netcoop.diagnosis.params import DiagnosisParams

_CLASS_RANK = {"direct_measurement": 0, "derived": 1, "user_report": 2}


@dataclass(frozen=True)
class Evidence:
    entity: str
    item: str
    severities: tuple[Severity, ...]
    observation_ids: tuple[str, ...]
    agents: tuple[str, ...]
    caveat: bool = False

    def strength(self, mode: str, e_mid: float) -> float:
        """Evidence strength e in [0, 1]; unresolved conflicts use the weakest value."""
        if mode == "normal":
            return min(1.0 if s == "normal" else 0.0 for s in self.severities)
        table = {"normal": 0.0, "elevated": e_mid, "critical": 1.0, "unknown": 0.0}
        return min(table[s] for s in self.severities)

    @property
    def abnormal(self) -> bool:
        return all(s in ("elevated", "critical") for s in self.severities)


@dataclass
class EvidenceView:
    items: dict[tuple[str, str], Evidence]
    not_assessable: dict[tuple[str, str], str]
    facts: dict[str, Any]
    conflicts: list[ConflictRecord]
    entities: list[str]
    items_per_entity: list[str]
    agents_reporting: set[str] = field(default_factory=set)

    def get(self, entity: str, item: str) -> Evidence | None:
        return self.items.get((entity, item))

    @property
    def total_pairs(self) -> int:
        return max(1, len(self.entities) * len(self.items_per_entity))


def build_view(
    observations: list[Observation],
    not_assessable: list[NotAssessableItem],
    *,
    facts: dict[str, Any],
    params: DiagnosisParams,
    entities: list[str],
    items_per_entity: list[str],
) -> EvidenceView:
    groups: dict[tuple[str, str], list[Observation]] = defaultdict(list)
    na: dict[tuple[str, str], str] = {}
    for o in observations:
        if o.assessability == "not_assessable" or o.severity == "unknown":
            na[(o.entity, o.metric)] = "unknown" if o.severity == "unknown" else "not_assessable"
            continue
        groups[(o.entity, o.metric)].append(o)
    for item in not_assessable:
        na.setdefault((item.entity, item.metric), item.reason)

    conflicts: list[ConflictRecord] = []
    view_items: dict[tuple[str, str], Evidence] = {}
    tolerance = timedelta(seconds=params.conflicts.freshness_tolerance_s)
    for key in sorted(groups):
        obs = sorted(groups[key], key=lambda o: o.observation_id)
        kept = obs
        if len({o.severity for o in obs}) > 1:
            kept, records = _resolve(key, obs, tolerance, len(conflicts))
            conflicts.extend(records)
        na.pop(key, None)
        view_items[key] = Evidence(
            entity=key[0],
            item=key[1],
            severities=tuple(o.severity for o in kept),
            observation_ids=tuple(o.observation_id for o in kept),
            agents=tuple(sorted({o.agent for o in kept})),
            caveat=any(o.assessability == "assessed_with_caveat" for o in kept),
        )
    return EvidenceView(
        items=view_items,
        not_assessable=na,
        facts=facts,
        conflicts=conflicts,
        entities=entities,
        items_per_entity=items_per_entity,
        agents_reporting={o.agent for o in observations},
    )


def _resolve(
    key: tuple[str, str], obs: list[Observation], tolerance: timedelta, offset: int
) -> tuple[list[Observation], list[ConflictRecord]]:
    entity, item = key
    records: list[ConflictRecord] = []
    ids = [o.observation_id for o in obs]

    def record(rule: str, kept: list[Observation], dropped: list[Observation], why: str) -> None:
        records.append(
            ConflictRecord(
                conflict_id=f"CONF-{offset + len(records) + 1:03d}",
                description=f"{entity} {item}: observations disagree "
                f"({', '.join(f'{o.observation_id}={o.severity}' for o in obs)})",
                observation_ids=ids,
                rule=rule,
                resolution=f"kept {[o.observation_id for o in kept]}",
                disregarded={o.observation_id: why for o in dropped},
            )
        )

    best = min(_CLASS_RANK[o.evidence_class] for o in obs)
    by_class = [o for o in obs if _CLASS_RANK[o.evidence_class] == best]
    if len(by_class) < len(obs):
        dropped = [o for o in obs if o not in by_class]
        record("evidence_class", by_class, dropped, "weaker evidence class than direct measurement")
        obs = by_class
        if len({o.severity for o in obs}) == 1:
            return obs, records

    newest = max(o.window.end for o in obs)
    fresh = [o for o in obs if newest - o.window.end <= tolerance]
    if len(fresh) < len(obs):
        dropped = [o for o in obs if o not in fresh]
        record("freshness", fresh, dropped, "older than a fresher conflicting observation")
        obs = fresh
        if len({o.severity for o in obs}) == 1:
            return obs, records

    record("unresolved", obs, [], "")
    records[-1] = records[-1].model_copy(
        update={
            "resolution": "unresolved: both kept; weaker evidence used for scoring and "
            "stated as a limitation"
        }
    )
    return obs, records

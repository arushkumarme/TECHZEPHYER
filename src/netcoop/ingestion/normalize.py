"""Ingestion: parse → structure → version → field mapping → units → timestamps →
plausibility → de-duplication → assessability → data-quality note → acceptance (doc 05 §6).

Deterministic code, not an agent. Two rules dominate everything here (CD-10):
a partly missing metric never invalidates a bundle, and missing is never healthy.
"""

from __future__ import annotations

import json
import math
import re
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Literal, cast

from pydantic import ValidationError

from netcoop.config.fields import FieldDictionary, load_field_dictionary
from netcoop.config.settings import Settings, load_settings
from netcoop.core.blocks import TimeWindow
from netcoop.core.vocab import NotAssessableReason
from netcoop.ingestion.aliases import AliasConfig, load_aliases
from netcoop.ingestion.issues import IngestIssue, issue
from netcoop.ingestion.models import (
    STATUS_ITEM,
    DataQualityNote,
    IngestResult,
    MetricState,
    NormalizedBundle,
    NormalizedRecord,
    ProbeResult,
)

_VERSION_RE = re.compile(r"^(\d+)\.(\d+)$")
_CORE_KEYS = {"timestamp", "device_id", "metrics", "status", "units"}
_META_KEYS = {
    "records",
    "schema_version",
    "mode",
    "provenance",
    "reference_time",
    "topology_ref",
    "probes",
    "description",
}
_STATUS_VALUES = {"healthy": "Healthy", "warning": "Warning", "critical": "Critical"}
#: When several records fail differently, the reported reason follows this priority.
_FAIL_PRIORITY: tuple[NotAssessableReason, ...] = ("UNIT_AMBIGUOUS", "MALFORMED", "IMPLAUSIBLE")


@dataclass
class _Rec:
    index: int
    entity: str
    timestamp: datetime
    status: str | None
    metrics: dict[str, float]
    failures: dict[str, NotAssessableReason] = field(default_factory=dict)
    unmapped: list[str] = field(default_factory=list)
    flags: set[str] = field(default_factory=set)


def _reject(code: str, message: str, issues: list[IngestIssue]) -> IngestResult:
    issues = [*issues, issue(code, message)]
    return IngestResult(acceptance="REJECTED", bundle=None, issues=issues, rejection_code=code)


def parse_timestamp(value: Any) -> datetime | None:
    """ISO 8601 with an explicit offset or ``Z``. Naive or unparseable → None (not guessed)."""
    if not isinstance(value, str):
        return None
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return dt if dt.tzinfo is not None else None


def _numeric(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    if math.isnan(value) or math.isinf(value):
        return None
    return float(value)


def ingest(
    raw: str | bytes,
    *,
    settings: Settings | None = None,
    fields: FieldDictionary | None = None,
    aliases: AliasConfig | None = None,
) -> IngestResult:
    """Validate and normalize one telemetry bundle."""
    settings = settings or load_settings()
    fields = fields or load_field_dictionary()
    aliases = aliases or load_aliases()
    issues: list[IngestIssue] = []

    # ---- 1. parse + 2. structure --------------------------------------------------
    try:
        doc = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        return _reject("INPUT_UNPARSEABLE", f"not valid JSON: {exc}", issues)
    meta: dict[str, Any]
    if isinstance(doc, list):
        meta, raw_records = {}, doc
    elif isinstance(doc, dict) and isinstance(doc.get("records"), list):
        meta, raw_records = doc, doc["records"]
    else:
        return _reject(
            "INPUT_UNPARSEABLE",
            "expected a JSON array of records or an object with 'records'",
            issues,
        )
    for key in sorted(set(meta) - _META_KEYS):
        issues.append(issue("FIELD_IGNORED", f"unknown bundle key {key!r} ignored", field=key))

    mode = meta.get("mode")
    if mode is not None and mode != settings.mode:
        return _reject(
            "INPUT_MODE_UNSUPPORTED", f"mode {mode!r} refused; only 'simulation'", issues
        )

    # ---- 3. schema version ---------------------------------------------------------
    schema_version = meta.get("schema_version")
    flat_adapter = False
    if schema_version is not None:
        m = _VERSION_RE.match(str(schema_version))
        major = int(m.group(1)) if m else None
        if major in settings.ingestion.supported_bundle_majors:
            pass
        elif major in settings.ingestion.adapter_bundle_majors:
            flat_adapter = True
            issues.append(
                issue(
                    "SCHEMA_ADAPTER_APPLIED",
                    f"bundle schema {schema_version}: team-authored flat layout adapted",
                )
            )
        else:
            return _reject(
                "INPUT_SCHEMA_VERSION_UNSUPPORTED",
                f"bundle schema_version {schema_version!r} has no supported major or adapter",
                issues,
            )

    # ---- 4-7. per-record mapping, units, timestamps, plausibility -------------------
    metric_specs = {n: s for n, s in fields.fields.items() if s.location == "metrics"}
    entity_seen = False
    recs: list[_Rec] = []
    for i, raw_rec in enumerate(raw_records):
        if not isinstance(raw_rec, dict):
            issues.append(issue("ENTITY_UNUSABLE", "record is not an object", record_index=i))
            continue
        rec = dict(raw_rec)
        for alias, canonical in aliases.record_aliases.items():
            if alias in rec and canonical not in rec:
                rec[canonical] = rec.pop(alias)
                issues.append(
                    issue(
                        "FIELD_ALIAS_APPLIED",
                        f"{alias!r} mapped to {canonical!r} ({aliases.provenance})",
                        record_index=i,
                        field=alias,
                    )
                )
        if flat_adapter:
            rec["metrics"] = {k: v for k, v in rec.items() if k not in _CORE_KEYS}
            rec = {k: v for k, v in rec.items() if k in _CORE_KEYS}
        for key in sorted(set(rec) - _CORE_KEYS):
            issues.append(
                issue("FIELD_IGNORED", f"unknown record key {key!r}", record_index=i, field=key)
            )

        entity = rec.get("device_id")
        if not isinstance(entity, str) or not entity.strip():
            issues.append(issue("ENTITY_UNUSABLE", "no usable device_id", record_index=i))
            continue
        entity_seen = True
        ts = parse_timestamp(rec.get("timestamp"))
        if ts is None:
            issues.append(
                issue(
                    "TIMESTAMP_UNUSABLE",
                    f"timestamp {rec.get('timestamp')!r} missing, unparseable or without timezone",
                    record_index=i,
                    entity=entity,
                )
            )
            continue

        out = _Rec(index=i, entity=entity, timestamp=ts, status=None, metrics={})
        declared_units = rec.get("units") if isinstance(rec.get("units"), dict) else {}
        assert isinstance(declared_units, dict)
        raw_metrics = rec.get("metrics")
        if not isinstance(raw_metrics, dict):
            raw_metrics = {}
        for key, value in raw_metrics.items():
            implied: str | None
            if key in metric_specs:
                canonical, implied = key, metric_specs[key].unit
            elif key in aliases.metric_aliases:
                al = aliases.metric_aliases[key]
                canonical, implied = al.canonical, al.unit
                issues.append(
                    issue(
                        "FIELD_ALIAS_APPLIED",
                        f"{key!r} mapped to {canonical!r} ({aliases.provenance})",
                        record_index=i,
                        entity=entity,
                        field=key,
                    )
                )
            else:
                out.unmapped.append(key)
                issues.append(
                    issue(
                        "FIELD_UNMAPPED",
                        f"metric field {key!r} has no listed alias; not interpreted",
                        record_index=i,
                        entity=entity,
                        field=key,
                    )
                )
                continue
            if canonical in out.metrics or canonical in out.failures:
                issues.append(
                    issue(
                        "FIELD_IGNORED",
                        f"{key!r} duplicates {canonical!r} in the same record",
                        record_index=i,
                        field=key,
                    )
                )
                continue
            spec = metric_specs[canonical]
            target = aliases.unit(spec.unit)
            declared = declared_units.get(key)
            implied_u, declared_u = aliases.unit(implied), aliases.unit(declared)
            unit: tuple[str, float] | None
            if implied is not None and declared is not None:
                unit = implied_u if implied_u == declared_u else None
            elif implied is not None:
                unit = implied_u
            elif declared is not None:
                unit = declared_u
            else:
                unit = None
            if unit is None or target is None or unit[0] != target[0]:
                out.failures[canonical] = "UNIT_AMBIGUOUS"
                out.flags.add("UNIT_AMBIGUOUS")
                issues.append(
                    issue(
                        "UNIT_AMBIGUOUS",
                        f"{key!r}: unit unknown or contradictory "
                        f"(implied={implied!r}, declared={declared!r})",
                        record_index=i,
                        entity=entity,
                        field=key,
                    )
                )
                continue
            number = _numeric(value)
            if number is None:
                out.failures[canonical] = "MALFORMED"
                out.flags.add("MALFORMED")
                issues.append(
                    issue(
                        "VALUE_MALFORMED",
                        f"{key!r} value {value!r} is not a finite number",
                        record_index=i,
                        entity=entity,
                        field=key,
                    )
                )
                continue
            factor = unit[1] / target[1]
            if factor != 1.0:
                number *= factor
                issues.append(
                    issue(
                        "UNIT_CONVERTED",
                        f"{key!r}: {value} {declared or implied} -> {number:g} {spec.unit}",
                        record_index=i,
                        entity=entity,
                        field=key,
                    )
                )
            lo, hi = spec.plausible_min, spec.plausible_max
            if (lo is not None and number < lo) or (hi is not None and number > hi):
                out.failures[canonical] = "IMPLAUSIBLE"
                out.flags.add("IMPLAUSIBLE")
                issues.append(
                    issue(
                        "VALUE_IMPLAUSIBLE",
                        f"{canonical}={number:g} outside plausible range [{lo}, {hi}]",
                        record_index=i,
                        entity=entity,
                        field=canonical,
                    )
                )
                continue
            out.metrics[canonical] = number

        raw_status = rec.get("status")
        if raw_status is not None:
            norm = _STATUS_VALUES.get(raw_status.lower()) if isinstance(raw_status, str) else None
            if norm is None:
                out.failures[STATUS_ITEM] = "MALFORMED"
                out.flags.add("MALFORMED")
                issues.append(
                    issue(
                        "STATUS_UNRECOGNIZED",
                        f"status {raw_status!r} not Healthy/Warning/Critical; treated as unknown",
                        record_index=i,
                        entity=entity,
                        field="status",
                    )
                )
            else:
                out.status = norm
        recs.append(out)

    if not entity_seen:
        return _reject("INPUT_NO_ENTITY", "no record identifies a device", issues)
    if not recs:
        return _reject("INPUT_NO_TIMESTAMP", "no record has a usable timestamp", issues)

    # ---- 8. de-duplication ---------------------------------------------------------
    kept: list[_Rec] = []
    seen: dict[tuple[Any, ...], _Rec] = {}
    by_key: dict[tuple[str, datetime], list[_Rec]] = defaultdict(list)
    for r in recs:
        fingerprint = (
            r.entity,
            r.timestamp,
            r.status,
            tuple(sorted(r.metrics.items())),
            tuple(sorted(r.failures.items())),
        )
        if fingerprint in seen:
            issues.append(
                issue(
                    "RECORD_DUPLICATE",
                    f"record {r.index} duplicates record {seen[fingerprint].index}; removed",
                    record_index=r.index,
                    entity=r.entity,
                )
            )
            continue
        seen[fingerprint] = r
        by_key[(r.entity, r.timestamp)].append(r)
        kept.append(r)
    for (entity, ts), group in by_key.items():
        if len(group) > 1:
            for r in group:
                r.flags.add("CONFLICT")
            issues.append(
                issue(
                    "RECORD_CONFLICT",
                    f"{len(group)} different records for {entity} at {ts.isoformat()} "
                    f"(records {[r.index for r in group]}); all kept for conflict resolution",
                    entity=entity,
                )
            )

    if not any(r.metrics or r.status for r in kept):
        return _reject("INPUT_NO_USABLE_METRIC", "no record carries a usable metric", issues)

    # ---- freshness --------------------------------------------------------------------
    latest_ts = max(r.timestamp for r in kept)
    reference = parse_timestamp(meta.get("reference_time")) or latest_ts
    stale_after = timedelta(seconds=settings.ingestion.stale_after_s)
    entities = sorted({r.entity for r in kept})
    newest = {e: max(r.timestamp for r in kept if r.entity == e) for e in entities}
    stale = {e for e in entities if reference - newest[e] > stale_after}
    for e in sorted(stale):
        issues.append(
            issue(
                "DATA_STALE",
                f"newest record for {e} is {reference - newest[e]} older than the reference",
                entity=e,
            )
        )

    # ---- assessability per entity-item ----------------------------------------------
    items = [*metric_specs, STATUS_ITEM]
    states: dict[tuple[str, str], MetricState] = {}
    for e in entities:
        mine = [r for r in kept if r.entity == e]
        has_unmapped = any(r.unmapped for r in mine)
        for item in items:
            present = any(
                (r.status is not None) if item == STATUS_ITEM else (item in r.metrics) for r in mine
            )
            if present:
                states[(e, item)] = (
                    MetricState(assessability="assessed_with_caveat", reason="STALE")
                    if e in stale
                    else MetricState(assessability="assessed")
                )
                continue
            failures = [r.failures[item] for r in mine if item in r.failures]
            reason: NotAssessableReason
            detail = ""
            if failures:
                reason = next(p for p in _FAIL_PRIORITY if p in failures)
            elif has_unmapped and item != STATUS_ITEM:
                reason = "UNMAPPED_FIELD"
                names = sorted({n for r in mine for n in r.unmapped})
                detail = f"absent; record(s) carry unmapped fields {names}"
            else:
                reason = "MISSING"
            states[(e, item)] = MetricState(
                assessability="not_assessable", reason=reason, detail=detail
            )

    for item in items:
        assessed_somewhere = any(
            states[(e, item)].assessability != "not_assessable" for e in entities
        )
        missing_for = [
            e for e in entities if states[(e, item)].reason in ("MISSING", "UNMAPPED_FIELD")
        ]
        if not missing_for:
            continue
        if assessed_somewhere:
            issues.append(
                issue(
                    "METRIC_MISSING",
                    f"{item} missing for {missing_for} while present for other devices",
                    field=item,
                )
            )
        elif len(missing_for) == len(entities):
            issues.append(
                issue(
                    "METRIC_NOT_PROVIDED",
                    f"{item} is not present in this bundle for any device; not assessable",
                    field=item,
                )
            )

    # ---- probes (team-authored service checks, doc 08 §3.3) ---------------------------
    probes: list[ProbeResult] = []
    raw_probes = meta.get("probes") or []
    for j, p in enumerate(raw_probes if isinstance(raw_probes, list) else [raw_probes]):
        try:
            if not isinstance(p, dict):
                raise ValueError("probe is not an object")
            data = {k: v for k, v in p.items() if k != "provenance"}
            if parse_timestamp(data.get("timestamp")) is None:
                raise ValueError("probe timestamp missing or without timezone")
            probes.append(ProbeResult.model_validate(data))
        except (ValidationError, ValueError) as exc:
            issues.append(issue("PROBE_INVALID", f"probe {j} dropped: {str(exc).splitlines()[0]}"))

    # ---- data-quality note + acceptance ------------------------------------------------
    n_pairs = len(entities) * len(items)
    assessed_pairs = sum(1 for s in states.values() if s.assessability != "not_assessable")
    bad_records = sum(
        1 for r in kept if r.flags & {"IMPLAUSIBLE", "MALFORMED", "UNIT_AMBIGUOUS", "CONFLICT"}
    )
    warnings = sorted({i.code for i in issues if i.severity == "warning"})
    acceptance: Literal["READY", "READY_WITH_WARNINGS"] = (
        "READY_WITH_WARNINGS" if warnings else "READY"
    )
    note = DataQualityNote(
        completeness=assessed_pairs / n_pairs,
        freshness=1 - len(stale) / len(entities),
        consistency=1 - bad_records / len(kept),
        acceptance=acceptance,
        warnings=warnings,
    )
    normalized = [
        NormalizedRecord(
            record_id=f"REC-{n:04d}",
            source_index=r.index,
            entity=r.entity,
            timestamp=r.timestamp,
            status=cast(Any, r.status),
            metrics=r.metrics,
            flags=sorted(r.flags),
        )
        for n, r in enumerate(sorted(kept, key=lambda r: r.index), start=1)
    ]
    provenance = meta.get("provenance")
    topology_ref = meta.get("topology_ref")
    bundle = NormalizedBundle(
        schema_version=None if schema_version is None else str(schema_version),
        provenance=provenance if isinstance(provenance, str) else "unspecified",
        topology_ref=topology_ref if isinstance(topology_ref, str) else None,
        records=normalized,
        entities=entities,
        window=TimeWindow(start=min(r.timestamp for r in kept), end=max(r.timestamp for r in kept)),
        metric_states=states,
        probes=probes,
        data_quality=note,
        assessable_items=items,
    )
    return IngestResult(acceptance=acceptance, bundle=bundle, issues=issues)

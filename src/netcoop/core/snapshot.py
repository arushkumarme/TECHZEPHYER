"""Data snapshot ID: one fingerprint of exactly the data every agent analyses (doc 05 §1).

Telemetry and topology are never carried inside messages. Instead every message of an
incident carries the same ``snapshot_id``, the first 12 hex characters of a SHA-256 over
the canonical JSON of the normalized bundle. Any agent, log reader or replay can check it
is looking at the same data.

Canonical JSON: sorted keys, ``(",", ":")`` separators, UTF-8, NaN/Infinity rejected.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime
from typing import Any

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from netcoop.config.settings import Settings
from netcoop.core.ids import Clock
from netcoop.core.vocabulary import is_valid
from netcoop.diagnosis.params import DiagnosisParams
from netcoop.ingestion.models import NormalizedBundle
from netcoop.tools.topology import Topology


class CanonicalHashError(ValueError):
    pass


def canonical_json(obj: Any) -> str:
    try:
        return json.dumps(
            obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
        )
    except ValueError as exc:  # NaN / Infinity
        raise CanonicalHashError(f"value cannot be hashed canonically: {exc}") from exc


def canonical_hash(obj: Any) -> str:
    return hashlib.sha256(canonical_json(obj).encode("utf-8")).hexdigest()


def bundle_canonical(bundle: NormalizedBundle) -> dict[str, Any]:
    """Everything the agents can read from the bundle, as plain JSON-able data."""
    return {
        "schema_version": bundle.schema_version,
        "provenance": bundle.provenance,
        "topology_ref": bundle.topology_ref,
        "entities": bundle.entities,
        "assessable_items": bundle.assessable_items,
        "window": bundle.window.model_dump(mode="json"),
        "records": [r.model_dump(mode="json") for r in bundle.records],
        "probes": [p.model_dump(mode="json") for p in bundle.probes],
        "metric_states": sorted(
            [e, i, s.model_dump(mode="json")] for (e, i), s in bundle.metric_states.items()
        ),
        "data_quality": bundle.data_quality.model_dump(mode="json"),
    }


#: Execution mechanics that tests prove do not change any finding, decision or report
#: (parallel vs sequential: test_sequential_and_parallel_runs_are_identical; direct vs MCP:
#: tests/mcp T-MCP-04/05). They are left out of the config fingerprint.
RESULT_NEUTRAL_SETTINGS = ("parallel_specialists", "tool_transport")


def analysis_config_hash(settings: Settings, params: DiagnosisParams) -> str:
    """12-hex fingerprint of the configuration that can change the analysis."""
    data = settings.model_dump(mode="json")
    for key in RESULT_NEUTRAL_SETTINGS:
        data["orchestration"].pop(key, None)
    return canonical_hash(
        {"settings": data, "diagnosis": params.model_dump(mode="json", by_alias=True)}
    )[:12]


class DataSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    snapshot_id: str = Field(pattern=r"^SNAP-[0-9a-f]{12}$")
    bundle_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    topology_version: str = Field(description="12-hex topology hash, or 'none'")
    config_hash: str = Field(description="12-hex hash of effective settings + diagnosis params")
    mode: str
    data_provenance: str = Field(description="Registered data_provenance term stamped on messages")
    declared_provenance: str = Field(description="Provenance string as declared by the bundle")
    bundle_acceptance: str
    source_label: str
    created_at: AwareDatetime


def take_snapshot(
    bundle: NormalizedBundle,
    topology: Topology | None,
    *,
    settings: Settings,
    params: DiagnosisParams,
    source_label: str,
    clock: Clock,
    acceptance: str | None = None,
) -> DataSnapshot:
    bundle_hash = canonical_hash(bundle_canonical(bundle))
    declared = bundle.provenance
    created: datetime = clock.now()
    return DataSnapshot(
        snapshot_id=f"SNAP-{bundle_hash[:12]}",
        bundle_hash=bundle_hash,
        topology_version=(
            canonical_hash(topology.model_dump(mode="json"))[:12] if topology else "none"
        ),
        config_hash=analysis_config_hash(settings, params),
        mode=settings.mode,
        data_provenance=declared if is_valid("data_provenance", declared) else "unspecified",
        declared_provenance=declared,
        bundle_acceptance=acceptance or bundle.data_quality.acceptance,
        source_label=source_label,
        created_at=created,
    )

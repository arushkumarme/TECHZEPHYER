"""Ingestion error taxonomy (doc 05 §7) with fixed severities."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict

IssueSeverity = Literal["fatal", "error", "warning", "info"]

SEVERITY: dict[str, IssueSeverity] = {
    # fatal -> bundle REJECTED
    "INPUT_UNPARSEABLE": "fatal",
    "INPUT_SCHEMA_VERSION_UNSUPPORTED": "fatal",
    "INPUT_NO_ENTITY": "fatal",
    "INPUT_NO_TIMESTAMP": "fatal",
    "INPUT_NO_USABLE_METRIC": "fatal",
    "INPUT_MODE_UNSUPPORTED": "fatal",
    # warnings -> READY_WITH_WARNINGS
    "SCHEMA_ADAPTER_APPLIED": "warning",
    "FIELD_ALIAS_APPLIED": "warning",
    "FIELD_UNMAPPED": "warning",
    "UNIT_AMBIGUOUS": "warning",
    "METRIC_MISSING": "warning",
    "VALUE_IMPLAUSIBLE": "warning",
    "VALUE_MALFORMED": "warning",
    "STATUS_UNRECOGNIZED": "warning",
    "DATA_STALE": "warning",
    "TIMESTAMP_UNUSABLE": "warning",
    "ENTITY_UNUSABLE": "warning",
    "RECORD_CONFLICT": "warning",
    "PROBE_INVALID": "warning",
    "TOPOLOGY_MISSING": "warning",
    "ENTITY_NOT_IN_TOPOLOGY": "warning",
    # info -> recorded only
    "UNIT_CONVERTED": "info",
    "RECORD_DUPLICATE": "info",
    "FIELD_IGNORED": "info",
    "METRIC_NOT_PROVIDED": "info",
}


class IngestIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    severity: IssueSeverity
    message: str
    record_index: int | None = None
    entity: str | None = None
    field: str | None = None


def issue(
    code: str,
    message: str,
    *,
    record_index: int | None = None,
    entity: str | None = None,
    field: str | None = None,
) -> IngestIssue:
    return IngestIssue(
        code=code,
        severity=SEVERITY[code],
        message=message,
        record_index=record_index,
        entity=entity,
        field=field,
    )

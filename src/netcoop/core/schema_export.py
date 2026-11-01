"""Export formal JSON Schemas for the envelope, every payload type and the official report
(conformance kit, doc 05 §17). Each file states the protocol version it describes.

Run ``uv run python scripts/export_schemas.py`` (or ``-m netcoop.core.schema_export``) after
changing a protocol model; ``tests/core/test_ids_schema.py`` and
``tests/conformance/test_kit.py`` fail while the committed copies are stale.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from netcoop.core.messages import PAYLOAD_TYPES, Envelope
from netcoop.core.versioning import PAYLOAD_SCHEMA_VERSION, PROTOCOL_VERSION
from netcoop.scenarios.generator import REPO_ROOT

#: Single location of the committed schemas (moved from schemas/protocol/ in P6).
SCHEMA_DIR = REPO_ROOT / "conformance" / "schemas"


def _write(path: Path, model: type[BaseModel], extra: dict[str, Any]) -> Path:
    schema = model.model_json_schema(mode="validation")
    schema.update(extra)
    path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", "utf-8", newline="\n")
    return path


def _versions() -> dict[str, str]:
    return {
        "x-netcoop-protocol-version": PROTOCOL_VERSION,
        "x-netcoop-payload-schema-version": PAYLOAD_SCHEMA_VERSION,
    }


def export_schemas(out_dir: Path = SCHEMA_DIR) -> list[Path]:
    """The envelope and one schema per message type's payload."""
    out_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {"envelope": Envelope, **PAYLOAD_TYPES}
    return [_write(out_dir / f"{n}.schema.json", m, _versions()) for n, m in models.items()]


def export_report_schema(out_dir: Path = SCHEMA_DIR) -> Path:
    """The official ten-key report (doc 07 §1), strict."""
    from netcoop.report.official import OfficialReport

    out_dir.mkdir(parents=True, exist_ok=True)
    return _write(out_dir / "official_report.schema.json", OfficialReport, _versions())


def export_all(out_dir: Path = SCHEMA_DIR) -> list[Path]:
    return [*export_schemas(out_dir), export_report_schema(out_dir)]


if __name__ == "__main__":
    for p in export_all():
        print(p.relative_to(REPO_ROOT))

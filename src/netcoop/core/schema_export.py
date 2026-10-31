"""Export formal JSON Schemas for the envelope and every payload type (doc 05 header).

Run ``uv run python -m netcoop.core.schema_export`` after changing a protocol model;
``tests/core/test_ids_schema.py`` fails while the committed copies are stale.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel

from netcoop.core.messages import PAYLOAD_TYPES, Envelope
from netcoop.scenarios.generator import REPO_ROOT

SCHEMA_DIR = REPO_ROOT / "schemas" / "protocol"


def export_schemas(out_dir: Path = SCHEMA_DIR) -> list[Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    models: dict[str, type[BaseModel]] = {"envelope": Envelope, **PAYLOAD_TYPES}
    written = []
    for name, model in models.items():
        path = out_dir / f"{name}.schema.json"
        schema = model.model_json_schema(mode="validation")
        path.write_text(json.dumps(schema, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append(path)
    return written


if __name__ == "__main__":
    for p in export_schemas():
        print(p.relative_to(REPO_ROOT))

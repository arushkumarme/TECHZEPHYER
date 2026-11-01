"""Write the conformance kit's JSON Schemas to conformance/schemas/.

uv run python scripts/export_schemas.py
"""

from netcoop.core.schema_export import export_all
from netcoop.scenarios.generator import REPO_ROOT

if __name__ == "__main__":
    for p in export_all():
        print(p.relative_to(REPO_ROOT))

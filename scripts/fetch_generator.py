"""Download the organizers' synthetic-data generator notebook and verify it.

    uv run python scripts/fetch_generator.py

The notebook (linked from the hackathon PDF, p4 §5) carries no licence, so it is not
redistributed in this repository. It is stored at sample_data/generator/ (git-ignored)
only if its SHA-256 matches the copy inspected on 2026-10-31.
"""

from netcoop.scenarios.generator import DEFAULT_NOTEBOOK, EXPECTED_SHA256, ensure_notebook

path = ensure_notebook(DEFAULT_NOTEBOOK)
print(f"{path} (SHA-256 {EXPECTED_SHA256}) ready")

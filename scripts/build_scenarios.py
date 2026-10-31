"""Write the frozen scenario packages to sample_data/scenarios/ (doc 09 §3).

    uv run python scripts/build_scenarios.py

Deterministic: re-running produces byte-identical files (checked by
tests/e2e/test_scenarios.py::test_committed_scenarios_are_reproducible).
"""

from netcoop.scenarios.catalog import SCENARIOS, build_input, dumps, metadata
from netcoop.scenarios.runner import SCENARIO_DIR

for sid in SCENARIOS:
    folder = SCENARIO_DIR / sid
    folder.mkdir(parents=True, exist_ok=True)
    (folder / "input.json").write_text(dumps(build_input(sid)), encoding="utf-8", newline="\n")
    (folder / "scenario.json").write_text(dumps(metadata(sid)), encoding="utf-8", newline="\n")
    print(folder.relative_to(SCENARIO_DIR.parent.parent))

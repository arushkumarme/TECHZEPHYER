"""Load frozen scenario packages, run them, and check expected outcomes (doc 09 §3)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from netcoop.config.settings import Settings, load_settings
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.workflow import IncidentResult, Orchestrator
from netcoop.scenarios.generator import REPO_ROOT

SCENARIO_DIR = REPO_ROOT / "sample_data" / "scenarios"


@dataclass(frozen=True)
class Scenario:
    id: str
    path: Path
    meta: dict[str, Any]

    @property
    def input_bytes(self) -> bytes:
        return (self.path / "input.json").read_bytes()


def list_scenarios(directory: Path = SCENARIO_DIR) -> list[str]:
    return sorted(p.name for p in directory.iterdir() if (p / "scenario.json").is_file())


def load_scenario(scenario_id: str, directory: Path = SCENARIO_DIR) -> Scenario:
    path = directory / scenario_id
    meta = json.loads((path / "scenario.json").read_text(encoding="utf-8"))
    return Scenario(id=scenario_id, path=path, meta=meta)


def run_scenario(
    scenario: Scenario,
    store: LogStore,
    *,
    settings: Settings | None = None,
    extra_faults: dict[str, str] | None = None,
) -> IncidentResult:
    faults = {**scenario.meta.get("run", {}).get("fault_injection", {}), **(extra_faults or {})}
    orch = Orchestrator(store, settings=settings or load_settings(), fault_injection=faults)
    return orch.run(scenario.input_bytes, source=f"scenario:{scenario.id}", label=scenario.id)


def check_expectations(
    result: IncidentResult,
    expected: dict[str, Any],
    *,
    reference_confidence: dict[str, float] | None = None,
) -> list[str]:
    """Return human-readable failures; empty list = the scenario passed."""
    r = result.report
    ext = r.get("netcoop_extensions", {})
    fails: list[str] = []

    def need(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    need(
        r["status"] in expected.get("status", [r["status"]]),
        f"status {r['status']} not in {expected.get('status')}",
    )
    need(
        r["status"] not in expected.get("forbidden_status", []),
        f"status {r['status']} is forbidden",
    )
    if "top_cause" in expected:
        need(
            ext.get("top_cause_type") == expected["top_cause"],
            f"top cause {ext.get('top_cause_type')} != {expected['top_cause']}",
        )
    if "affected_devices" in expected:
        need(
            r["affected_devices"] == expected["affected_devices"],
            f"affected {r['affected_devices']} != {expected['affected_devices']}",
        )
    if "min_evidence_sources" in expected:
        need(
            len(r["evidence_sources"]) >= expected["min_evidence_sources"],
            f"evidence_sources {r['evidence_sources']} < {expected['min_evidence_sources']}",
        )
    hyps = {h["cause_type"]: h for h in ext.get("hypotheses", [])}
    for cause in expected.get("forbidden_causes", []):
        need(ext.get("top_cause_type") != cause, f"forbidden cause {cause} is the top cause")
        need(hyps.get(cause, {}).get("score", 0) == 0, f"forbidden cause {cause} was scored")
    for cause in expected.get("forbidden_causes_on_top", []):
        need(ext.get("top_cause_type") != cause, f"{cause} must not be the top cause")
    for text in expected.get("limitations_contain", []):
        need(any(text in lim for lim in r["limitations"]), f"no limitation contains {text!r}")
    warnings = set(ext.get("data_quality", {}).get("warnings", []))
    for w in expected.get("warnings", []):
        need(w in warnings, f"warning {w} missing (have {sorted(warnings)})")
    na = {(n["entity"], n["metric"]) for n in ext.get("not_assessable", [])}
    for pair in expected.get("not_assessable_contains", []):
        need(tuple(pair) in na, f"{pair} not listed as not assessable")
    if "root_cause_prefix" in expected:
        need(
            r["suspected_root_cause"].startswith(expected["root_cause_prefix"]),
            f"root cause does not start with {expected['root_cause_prefix']!r}",
        )
    if "clarifications_min" in expected:
        need(
            len(ext.get("clarifications", [])) >= expected["clarifications_min"],
            "too few clarifications",
        )
    for agent in expected.get("missing_agents", []):
        need(
            ext.get("agent_contributions", {}).get(agent, {}).get("status") == "missing",
            f"{agent} not reported missing",
        )
    if "conflicts_min" in expected:
        need(len(ext.get("conflicts", [])) >= expected["conflicts_min"], "too few conflicts")
    ref = expected.get("confidence_below_scenario")
    if ref and reference_confidence and ref in reference_confidence:
        need(
            r["confidence"] < reference_confidence[ref],
            f"confidence {r['confidence']} not below {ref} ({reference_confidence[ref]})",
        )
    return fails

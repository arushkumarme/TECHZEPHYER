"""The real agents fill the Prompt 3 payload fields, visible in real scenario runs."""

from __future__ import annotations

import json
from collections import defaultdict
from typing import Any

import pytest

from netcoop.core.log_store import LogStore
from netcoop.core.parse import try_parse
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario


def run(sid: str) -> tuple[Any, list[dict[str, Any]]]:
    store = LogStore(":memory:")
    r = Orchestrator(store).run(load_scenario(sid).input_bytes)
    msgs = [json.loads(m.raw_json) for m in store.messages(r.incident_id) if m.valid]
    for m in msgs:  # every logged message re-validates with the 1.1 semantic rules
        assert try_parse(m).ok, m["message_id"]
    return r, msgs


def by_type(msgs: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    out: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for m in msgs:
        out[m["message_type"]].append(m)
    return out


def test_tasks_findings_and_references_in_a_diagnosed_run() -> None:
    r, msgs = run("S-02")
    t = by_type(msgs)
    tasks = [m["payload"] for m in t["task_request"]]
    ids = [x["task_id"] for x in tasks]
    assert ids == [f"TASK-{i:04d}" for i in range(1, len(ids) + 1)]
    assert {x["task_kind"] for x in tasks} == {"investigate", "correlate", "report"}
    assert all(x["incident_context"]["trigger"] == "telemetry_bundle" for x in tasks)
    finding_ids = {m["message_id"] for m in t["finding"]}
    correlate = next(x for x in tasks if x["task_kind"] == "correlate")
    assert set(correlate["input_message_ids"]) == finding_ids
    report_task = next(x for x in tasks if x["task_kind"] == "report")
    decision_ids = {m["message_id"] for m in t["decision"]}
    assert set(report_task["input_message_ids"]) == finding_ids | decision_ids
    task_by_msg = {m["message_id"]: m["payload"]["task_id"] for m in t["task_request"]}
    for f in t["finding"]:
        assert f["payload"]["task_id"] == task_by_msg[f["in_reply_to"]]
        for h in f["payload"]["hypotheses"]:
            assert h["score_method"] == "agent_local_heuristic"
            assert [e["evidence_id"] for e in h["supporting"]] == h["supporting_observation_ids"]
    decision = t["decision"][0]["payload"]
    assert decision["decision"] == "diagnosed" and decision["abstention"] is None
    assert decision["decision_id"] == "DEC-0001" and decision["score_method"] == "heuristic"
    recs = t["report_ready"][0]["payload"]["recommendations"]
    assert recs and all(x["simulated"] and x["requires_human_approval"] for x in recs)
    assert [x["action_text"] for x in recs] == r.report["recommended_actions"]


@pytest.mark.parametrize("sid", ["S-07", "S-12"])
def test_abstaining_decisions_explain_themselves(sid: str) -> None:
    _, msgs = run(sid)
    d = by_type(msgs)["decision"][-1]["payload"]
    assert d["decision"] == "insufficient_evidence"
    failed = sorted(k for k, v in d["gate_checks"].items() if not v)
    assert d["abstention"]["reasons"] and len(d["abstention"]["reasons"]) == len(failed)
    assert d["abstention"]["evidence_that_would_change_decision"]


def test_clarifications_carry_ids_and_answerable() -> None:
    _, msgs = run("S-09")
    t = by_type(msgs)
    reqs = [m["payload"] for m in t["clarification_request"]]
    assert reqs and all(x["clarification_id"].startswith("CLR-") for x in reqs)
    resp = [m["payload"] for m in t["clarification_response"]]
    assert {x["clarification_id"] for x in resp} <= {x["clarification_id"] for x in reqs}
    assert all(x["answerable"] in ("yes", "no", "partial") for x in resp)
    assert all(x["source"] for x in resp)


def test_status_unknown_observations_name_their_reason() -> None:
    found = []
    for sid in ("S-08",):
        _, msgs = run(sid)
        for m in by_type(msgs)["finding"]:
            found += [
                o for o in m["payload"]["observations"] if o["assessability"] == "not_assessable"
            ]
    assert found and all(o["not_assessable_reason"] for o in found)

"""Conflict messages and protocol 1.2 (protocol upgrade, Prompt 8)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from netcoop.conformance import KIT_DIR
from netcoop.core.blocks import Hypothesis
from netcoop.core.guard import ConversationGuard, ConversationState
from netcoop.core.log_store import LogStore
from netcoop.core.messages import ConflictReport, ConflictResponse, Envelope
from netcoop.core.parse import try_parse
from netcoop.core.versioning import PROTOCOL_VERSION
from netcoop.orchestrator.trace import render_trace
from netcoop.orchestrator.workflow import Orchestrator
from netcoop.scenarios.runner import load_scenario

VALID = KIT_DIR / "examples" / "valid"


def example(name: str) -> dict[str, Any]:
    return dict(json.loads((VALID / f"{name}.json").read_text("utf-8")))


# ------------------------------------------------------------------ payload rules


def test_only_competes_or_contradicts_is_a_conflict() -> None:
    base = example("conflict_report")["payload"]
    ConflictReport.model_validate(base)
    for relation in ("competes", "contradicts"):
        ConflictReport.model_validate(
            base | {"conflict_type": "hypothesis_competition", "relation": relation}
        )
    for relation in ("compatible", "refines"):
        with pytest.raises(ValidationError) as exc:
            ConflictReport.model_validate(base | {"relation": relation})
        assert exc.value.errors()[0]["type"] == "CONFLICT_RELATION_NOT_CONFLICTING"
    with pytest.raises(ValidationError) as exc:
        ConflictReport.model_validate(base | {"conflict_type": "hypothesis_competition"})
    assert exc.value.errors()[0]["type"] == "CONFLICT_RELATION_NOT_CONFLICTING"


def test_report_shape_rules() -> None:
    base = example("conflict_report")["payload"]
    with pytest.raises(ValidationError) as exc:
        ConflictReport.model_validate(base | {"target": "connectivity_agent"})
    assert exc.value.errors()[0]["type"] == "CONFLICT_TARGET_NOT_PARTY"
    for bad in (
        {"conflict_id": "C-1"},
        {"conflict_type": "argument"},
        {"sides": base["sides"][:1]},
        {"status": "settled"},
        {"proposed_rule": "majority_vote"},
        {"reason_code": "readings disagree"},
    ):
        with pytest.raises(ValidationError):
            ConflictReport.model_validate(base | bad)
    with pytest.raises(ValidationError):
        ConflictResponse.model_validate(example("conflict_response")["payload"] | {"stance": "x"})


def test_hypothesis_relations_use_the_vocabulary() -> None:
    h = {
        "hypothesis_id": "HYP-PERF-000001-001",
        "cause_type": "link_congestion",
        "entities": ["SW_1"],
        "supporting_observation_ids": ["OBS-PERF-000001-001"],
        "local_score": 0.5,
        "rationale_code": "QUEUE_DROPS",
    }
    ok = Hypothesis.model_validate(
        h | {"relations": [{"hypothesis_id": "HYP-INFRA-000002-001", "relation": "compatible"}]}
    )
    assert ok.relations[0].relation == "compatible"
    with pytest.raises(ValidationError):
        Hypothesis.model_validate(
            h | {"relations": [{"hypothesis_id": "HYP-X", "relation": "agrees"}]}
        )


# ------------------------------------------------------------------ version compatibility


def test_version_is_1_2_and_a_1_1_message_is_still_accepted() -> None:
    assert PROTOCOL_VERSION == "1.2"
    old = example("decision_with_abstention") | {"protocol_version": "1.1"}
    r = try_parse(old)
    assert r.ok and r.warnings == []


def test_a_reader_pinned_to_1_1_accepts_1_2_messages_with_unknown_field_warnings() -> None:
    msg = example("decision_with_conflict_trail")
    r = try_parse(msg, reader_version="1.1")
    assert r.ok
    codes = {(w.code, w.path) for w in r.warnings}
    assert ("PROTOCOL_MINOR_NEWER", "protocol_version") in codes
    assert ("FIELD_IGNORED", "payload.conflict_trail") in codes
    assert r.message is not None and r.message.envelope.payload.get("conflict_trail") is None
    finding = example("finding_with_not_assessable")
    finding["payload"]["hypotheses"][0]["relations"] = [
        {"hypothesis_id": "HYP-INFRA-000002-001", "relation": "compatible"}
    ]
    r2 = try_parse(finding, reader_version="1.1")
    assert r2.ok and ("FIELD_IGNORED", "payload.hypotheses.0.relations") in {
        (w.code, w.path) for w in r2.warnings
    }
    # a message type the 1.1 reader has never heard of is refused, plainly
    r3 = try_parse(example("conflict_report"), reader_version="1.1")
    assert not r3.ok and r3.errors[0].code == "UNKNOWN_TERM"
    assert "not known to a 1.1 reader" in r3.errors[0].reason
    # a 1.0 reader does not know the 1.1 envelope fields either
    r4 = try_parse(
        example("task_request_investigate") | {"protocol_version": "1.1"}, reader_version="1.0"
    )
    assert r4.ok and ("FIELD_IGNORED", "snapshot_id") in {(w.code, w.path) for w in r4.warnings}


# ------------------------------------------------------------------ conversation rules


def test_conflict_exchanges_count_toward_the_round_limit() -> None:
    steps = json.loads(
        (KIT_DIR / "examples/conversations/valid_real_conflict.json").read_text("utf-8")
    )["steps"]
    guard = ConversationGuard(max_clarification_rounds=0)
    state = ConversationState()
    for step in steps[:3]:
        env = Envelope.model_validate(step["message"])
        state = state.with_incident_state(step["incident_state"]).apply(env)
    report = Envelope.model_validate(steps[3]["message"])
    result = guard.check(report, state.with_incident_state("CORRELATING"))
    assert [v.code for v in result.violations] == ["CLARIFICATION_LIMIT_EXCEEDED"]


# ------------------------------------------------------------------ the real correlation agent


@pytest.fixture(scope="module")
def s12(tmp_path_factory: pytest.TempPathFactory) -> tuple[LogStore, Any]:
    store = LogStore(tmp_path_factory.mktemp("s12") / "s12.sqlite3")
    return store, Orchestrator(store).run(load_scenario("S-12").input_bytes)


def payloads(store: LogStore, incident: str, mtype: str) -> list[dict[str, Any]]:
    return [
        json.loads(m.raw_json)
        for m in store.messages(incident)
        if m.valid and m.message_type == mtype
    ]


def test_the_real_correlation_agent_raises_the_conflict(s12: tuple[LogStore, Any]) -> None:
    store, r = s12
    reports = payloads(store, r.incident_id, "conflict_report")
    assert [(m["sender"], m["recipient"]) for m in reports] == [
        ("correlation_agent", "orchestrator"),
        ("orchestrator", "performance_agent"),
    ]
    raised, relayed = reports
    assert relayed["in_reply_to"] == raised["message_id"]
    assert raised["payload"] == relayed["payload"]
    p = raised["payload"]
    assert p["conflict_type"] == "observation_contradiction" and p["proposed_rule"] == "unresolved"
    assert len(p["sides"]) == 2 and p["target"] == "performance_agent"
    (resp,) = payloads(store, r.incident_id, "conflict_response")
    assert resp["sender"] == "performance_agent" and resp["in_reply_to"] == relayed["message_id"]
    assert resp["payload"]["stance"] in ("maintain", "revise", "withdraw", "cannot_assess")
    assert resp["payload"]["conflict_id"] == p["conflict_id"]
    (clar,) = [
        x
        for x in payloads(store, r.incident_id, "clarification_request")
        if x["payload"]["reason"] == "conflict"
    ] or [None]
    assert clar is None  # the conflict re-check now travels as a conflict, not a question


def test_the_decision_keeps_the_conflict_in_its_trail(s12: tuple[LogStore, Any]) -> None:
    store, r = s12
    (decision,) = payloads(store, r.incident_id, "decision")
    (entry,) = decision["payload"]["conflict_trail"]
    assert entry["raised"] is True and entry["status"] == "unresolved_preserved"
    logged = {
        o["observation_id"]
        for m in payloads(store, r.incident_id, "finding")
        for o in m["payload"]["observations"]
    }
    logged |= {
        o["observation_id"]
        for m in payloads(store, r.incident_id, "conflict_response")
        for o in m["payload"]["observations"]
    }
    assert entry["preserved_observation_ids"] and set(entry["preserved_observation_ids"]) <= logged
    assert any(lim["code"] == "CONFLICT_UNRESOLVED" for lim in decision["payload"]["limitations"])
    assert r.report["status"] == "insufficient_evidence"  # outcome unchanged by the protocol


def test_conflicts_are_visible_in_the_traces(s12: tuple[LogStore, Any]) -> None:
    from netcoop.core.inspector import load_view, render_sequence, render_table

    store, r = s12
    view = load_view(store, r.incident_id)
    assert "CONFLICT CONF-001 observation_contradiction" in render_table(view)
    seq = render_sequence(view)
    assert "conflict_report !! CONF-001" in seq and "conflict_response !! CONF-001 stance" in seq
    assert "conflict_report" in render_trace(store, r.incident_id)


def test_conflict_runs_are_deterministic(tmp_path: Path) -> None:
    def order(name: str, parallel: bool) -> list[tuple[str, str]]:
        from netcoop.config.settings import load_settings

        s = load_settings()
        cfg = s.model_copy(
            update={
                "orchestration": s.orchestration.model_copy(
                    update={"parallel_specialists": parallel}
                )
            }
        )
        store = LogStore(tmp_path / name)
        r = Orchestrator(store, settings=cfg).run(load_scenario("S-12").input_bytes)
        return [(m.message_id or "", m.message_type or "") for m in store.messages(r.incident_id)]

    assert order("a.sqlite3", True) == order("b.sqlite3", False)
    assert order("c.sqlite3", True) == order("d.sqlite3", True)

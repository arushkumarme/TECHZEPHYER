"""Every vocabulary-controlled value in real orchestrated runs is a registered, non-blocked
term (protocol upgrade, Prompt 1 end-to-end proof)."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from netcoop.core.log_store import LogStore
from netcoop.core.vocabulary import get_vocabulary, is_valid
from netcoop.core.vocabulary.units import unit_fits_metric
from netcoop.scenarios.runner import load_scenario, run_scenario

pytestmark = pytest.mark.e2e


def _walk(payload: Any) -> Iterator[tuple[str, Any]]:
    if isinstance(payload, dict):
        for k, v in payload.items():
            yield k, v
            yield from _walk(v)
    elif isinstance(payload, list):
        for item in payload:
            yield from _walk(item)


FIELD_VOCAB = {
    "severity": "severity",
    "assessability": "assessability",
    "evidence_class": "evidence_class",
    "cause_type": "cause_type",
    "question_type": "question_type",
    "decision": "decision_kind",
    "confidence_category": "confidence_category",
    "rationale_code": "rationale_code",
    "target": "agent",
    "rule": "conflict_rule",
}


@pytest.mark.parametrize("sid", ["S-05", "S-09", "S-12"])
def test_logged_messages_use_only_registered_terms(sid: str, tmp_path: Path) -> None:
    store = LogStore(tmp_path / "v.sqlite3")
    result = run_scenario(load_scenario(sid), store)
    checked = 0
    for m in store.messages(result.incident_id):
        assert m.valid, (m.message_id, m.error_code)
        assert is_valid("message_type", m.message_type or "")
        assert is_valid("agent", m.sender or "") and is_valid("agent", m.recipient or "")
        envelope = json.loads(m.raw_json)
        assert is_valid("message_status", envelope["status"])
        for key, value in _walk(envelope["payload"]):
            if key in FIELD_VOCAB and isinstance(value, str):
                assert is_valid(FIELD_VOCAB[key], value), (m.message_type, key, value)
                checked += 1
            if key == "reason" and isinstance(value, str) and value.isupper():
                assert is_valid("not_assessable_reason", value), value
            if key == "observations" and isinstance(value, list):
                for o in value:
                    assert is_valid("metric", o["metric"]), o["metric"]
                    assert unit_fits_metric(o["metric"], o["unit"]), (o["metric"], o["unit"])
                    checked += 1
    assert checked > 50
    report_ext = result.report["netcoop_extensions"]
    assert is_valid("score_method", report_ext["confidence_method"])
    assert is_valid("report_status", result.report["status"])
    assert {t.id for t in get_vocabulary("recommendation_mode").terms} >= {
        report_ext["recommendation_mode"]
    }

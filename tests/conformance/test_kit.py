"""The protocol conformance kit (protocol upgrade, Prompt 6)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from netcoop.conformance import (
    KIT_DIR,
    MANIFEST_PATH,
    assert_agent_conforms,
    check_file,
    run_manifest,
)
from netcoop.conformance.build import main as build_main
from netcoop.core.guard import load_rules
from netcoop.core.messages import ParsedMessage
from netcoop.core.schema_export import export_all
from netcoop.scenarios.generator import REPO_ROOT


def test_the_manifest_matches_reality() -> None:
    results = run_manifest()
    bad = [(r.entry["path"], r.outcome.verdict, r.outcome.code) for r in results if not r.ok]
    assert bad == []
    manifest = json.loads(MANIFEST_PATH.read_text("utf-8"))
    kinds = {(e["kind"], e["expected_verdict"]) for e in manifest["examples"]}
    assert kinds == {
        ("message", "accepted"),
        ("message", "rejected"),
        ("conversation", "accepted"),
        ("conversation", "rejected"),
    }
    for e in manifest["examples"]:  # every file listed exists, every file is listed
        assert (KIT_DIR / e["path"]).exists()
    listed = {e["path"] for e in manifest["examples"]}
    on_disk = {p.relative_to(KIT_DIR).as_posix() for p in (KIT_DIR / "examples").rglob("*.json")}
    assert listed == on_disk


def test_examples_and_manifest_are_current() -> None:
    assert build_main(["--check"]) == 0


def test_schemas_are_current_and_state_their_version(tmp_path: Path) -> None:
    for fresh in export_all(tmp_path):
        committed = KIT_DIR / "schemas" / fresh.name
        assert committed.exists(), fresh.name
        data = json.loads(committed.read_text("utf-8"))
        assert data == json.loads(fresh.read_text("utf-8")), f"{fresh.name} is stale"
        assert data["x-netcoop-protocol-version"] == "1.2"  # was "1.1" before Prompt 8
    report = json.loads((KIT_DIR / "schemas" / "official_report.schema.json").read_text("utf-8"))
    assert len(report["properties"]) == 10 and report["additionalProperties"] is False


def test_breaking_a_rule_makes_the_kit_fail() -> None:
    rules = load_rules()
    broken = rules.model_copy(
        update={
            "rows": tuple(
                r.model_copy(update={"senders": ("correlation_agent", "performance_agent")})
                if r.message_type == "decision"
                else r
                for r in rules.rows
            )
        }
    )
    failed = [r.entry["path"] for r in run_manifest(rules=broken) if not r.ok]
    assert failed == ["examples/conversations/performance_agent_sends_decision.json"]


def test_breaking_a_model_makes_the_kit_fail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Swap the finding payload model for a permissive one: the invalid finding examples are
    then accepted, and the kit reports exactly those mismatches."""
    from pydantic import ConfigDict

    from netcoop.core.blocks import ProtocolModel
    from netcoop.core.messages import PAYLOAD_TYPES

    class AnythingGoes(ProtocolModel):
        model_config = ConfigDict(extra="allow", frozen=True)

    monkeypatch.setitem(PAYLOAD_TYPES, "finding", AnythingGoes)
    failed = {r.entry["path"] for r in run_manifest() if not r.ok}
    assert failed == {
        f"examples/invalid/{n}.json"
        for n in (
            "unknown_vocabulary_term",
            "unit_not_matching_metric",
            "not_assessable_with_value",
            "hypothesis_without_evidence",
            "evidence_wrong_prefix",
        )
    }


def test_cli_commands(tmp_path: Path) -> None:
    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, "-m", *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
            timeout=120,
            check=False,
        )

    ok = run("netcoop.cli.conformance")
    assert ok.returncode == 0, ok.stdout + ok.stderr
    assert "Result: PASS" in ok.stdout and "SIMULATED DATA" in ok.stdout
    assert "Rejected: only correlation_agent may send a decision" in ok.stdout
    bad = run("netcoop.cli.validate", "conformance/examples/invalid/mode_deployment.json")
    assert bad.returncode == 1 and "MODE_NOT_ALLOWED" in bad.stdout
    good = run("netcoop.cli.validate", "conformance/examples/valid/decision_with_abstention.json")
    assert good.returncode == 0 and good.stdout.startswith("ACCEPTED")
    # Honesty wording (doc 08 §9 / doc 12): never "live" or "real-time". ("calibrated" may
    # appear only as the blocked term the kit shows being rejected.)
    text = ok.stdout.lower().replace("never defaulted to live", "")
    assert "real-time" not in text and " live" not in text


# ------------------------------------------------------------------ third-party agents


RECORDED_TASK = KIT_DIR / "examples" / "valid" / "task_request_investigate.json"


def readme_stub_agent(task: ParsedMessage) -> dict[str, Any]:
    """A trivial 'third-party' agent written ONLY from conformance/README.md: it echoes the
    envelope fields, replies to the task and reports one status it could not assess."""
    t = task.envelope
    return {
        "protocol_version": "1.1",
        "message_id": f"{t.message_id}.R",
        "incident_id": t.incident_id,
        "in_reply_to": t.message_id,
        "sender": t.recipient,
        "recipient": "orchestrator",
        "message_type": "finding",
        "sent_at": "2026-11-01T09:01:00+00:00",
        "payload_schema_version": "1.0",
        "status": "partial",
        "snapshot_id": t.snapshot_id,
        "mode": "simulation",
        "data_provenance": t.data_provenance,
        "payload": {
            "task_id": t.payload.get("task_id"),
            "observations": [
                {
                    "observation_id": "OBS-STUB-000001-001",
                    "entity": "SW_CAMPUS_1",
                    "metric": "status",
                    "metric_category": "Device status",
                    "value": None,
                    "unit": "none",
                    "window": t.payload["window"],
                    "severity": "unknown",
                    "assessability": "not_assessable",
                    "not_assessable_reason": "MISSING",
                    "agent": t.recipient,
                }
            ],
            "hypotheses": [],
            "not_assessable": [{"entity": "SW_CAMPUS_1", "metric": "status", "reason": "MISSING"}],
            "limitations": [{"code": "METRIC_MISSING", "text": "stub agent has no data"}],
            "tool_calls": [],
            "self_assessment": {"assessed_fraction": 0.0, "budget_exhausted": False},
        },
    }


def test_a_stub_agent_written_from_the_readme_conforms() -> None:
    reply = assert_agent_conforms(readme_stub_agent, RECORDED_TASK.read_text("utf-8"))
    assert reply.envelope.message_type == "finding"


@pytest.mark.parametrize(
    ("change", "fragment"),
    [
        (lambda m: m.__setitem__("message_type", "decision"), "SENDER_NOT_AUTHORIZED"),
        (
            lambda m: m.__setitem__("recipient", "correlation_agent"),
            "DIRECT_AGENT_MESSAGE_FORBIDDEN",
        ),
        (
            lambda m: m["payload"]["observations"][0].__setitem__("value", "up"),
            "ASSESSABILITY_VALUE_MISMATCH",
        ),
        (lambda m: m.__setitem__("in_reply_to", "INC-0001-MSG-999999"), "REPLY_MISMATCH"),
    ],
)
def test_non_conforming_agents_are_caught(change: Any, fragment: str) -> None:
    def agent(task: ParsedMessage) -> dict[str, Any]:
        msg = readme_stub_agent(task)
        change(msg)
        if msg["message_type"] == "decision":
            msg["payload"] = {"decision": "diagnosed", "ranked": [], "margin": None}
        return msg

    with pytest.raises(AssertionError) as exc:
        assert_agent_conforms(agent, RECORDED_TASK.read_text("utf-8"))
    assert fragment in str(exc.value)


def test_validate_any_file_round_trip(tmp_path: Path) -> None:
    f = tmp_path / "msg.json"
    f.write_text(
        json.dumps(
            readme_stub_agent(
                __import__("netcoop.core.messages", fromlist=["parse_message"]).parse_message(
                    RECORDED_TASK.read_text("utf-8")
                )
            )
        ),
        "utf-8",
    )
    assert check_file(f).verdict == "accepted"

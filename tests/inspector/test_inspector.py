"""Protocol inspector (protocol upgrade, Prompt 7). Golden files: regenerate with
``NETCOOP_UPDATE_GOLDEN=1 uv run pytest tests/inspector``."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from netcoop.conformance import KIT_DIR
from netcoop.core.bus import GuardViolationError, MessageBus
from netcoop.core.guard import ConversationGuard
from netcoop.core.ids import FixedClock
from netcoop.core.inspector import (
    BANNER_TEXT,
    evidence_chain,
    explain_message,
    load_view,
    render_json,
    render_sequence,
    render_table,
)
from netcoop.core.log_store import LogStore
from netcoop.scenarios.generator import REPO_ROOT

GOLDEN = Path(__file__).parent / "golden"
T0 = datetime(2026, 11, 1, 9, tzinfo=UTC)
INC = "INC-0001"
CONVERSATION = KIT_DIR / "examples" / "conversations" / "valid_full_incident.json"


def build_fixture_log(path: Path) -> LogStore:
    """The kit's valid conversation through the REAL bus (parser + guard), with one
    rejected message (performance_agent sending a decision) inserted after the findings."""
    store = LogStore(path)
    steps = json.loads(CONVERSATION.read_text("utf-8"))["steps"]
    current = {"state": "READY"}
    bus = MessageBus(
        store,
        clock=FixedClock(T0, timedelta(milliseconds=250)),
        guard=ConversationGuard(),
        incident_state=lambda _: current["state"],
    )
    for i, step in enumerate(steps):
        current["state"] = step["incident_state"]
        bus.transmit(json.dumps(step["message"]))
        if i == 2:  # after the correlate task: the demo rejection
            forged = dict(
                steps[11]["message"],
                message_id=f"{INC}-MSG-000050",
                sender="performance_agent",
                in_reply_to=f"{INC}-MSG-000001",
            )
            with pytest.raises(GuardViolationError):
                bus.transmit(json.dumps(forged))
    return store


@pytest.fixture(scope="module")
def store(tmp_path_factory: pytest.TempPathFactory) -> LogStore:
    return build_fixture_log(tmp_path_factory.mktemp("insp") / "fixture.sqlite3")


def check_golden(name: str, text: str) -> None:
    path = GOLDEN / name
    if os.environ.get("NETCOOP_UPDATE_GOLDEN") or not path.exists():
        path.write_text(text, encoding="utf-8", newline="\n")
    assert text == path.read_text(encoding="utf-8"), f"{name} differs from the golden file"


def test_golden_table(store: LogStore) -> None:
    check_golden("table.txt", render_table(load_view(store, INC), show_rejected=True))


def test_golden_sequence(store: LogStore) -> None:
    check_golden("sequence.txt", render_sequence(load_view(store, INC), show_rejected=True))


def test_golden_json(store: LogStore) -> None:
    check_golden("trace.json", render_json(load_view(store, INC), show_rejected=True))


def test_rejected_messages_show_their_reason_and_toggle(store: LogStore) -> None:
    view = load_view(store, INC)
    shown = render_table(view, show_rejected=True)
    hidden = render_table(view)
    reason = "Rejected: only correlation_agent may send a decision; performance_agent tried."
    assert "REJECTED" in shown and "SENDER_NOT_AUTHORIZED" in shown and reason in shown
    assert "SENDER_NOT_AUTHORIZED" not in hidden.split("\n---")[0]
    assert "1 rejected" in hidden  # never silently hidden: the footer counts it
    seq = render_sequence(view, show_rejected=True)
    assert "X" in seq and "REJECTED SENDER_NOT_AUTHORIZED" in seq
    data = json.loads(render_json(view))
    (rej,) = [m for m in data["messages"] if m["verdict"] == "rejected"]
    assert rej["violations"][0]["reason"] == reason


def test_filters(store: LogStore) -> None:
    view = load_view(store, INC)
    only = render_table(view, types={"decision"}, show_rejected=True)
    body = [ln for ln in only.splitlines() if re.match(r"\s+\d+\s", ln)]
    assert body and all("decision" in ln for ln in body)
    by_sender = json.loads(render_json(view, sender="performance_agent", show_rejected=False))
    assert {m["sender"] for m in by_sender["messages"]} == {"performance_agent"}


def test_footer_counts(store: LogStore) -> None:
    data = json.loads(render_json(load_view(store, INC)))
    f = data["footer"]
    assert (f["messages"], f["accepted"], f["rejected"]) == (15, 14, 1)
    assert f["clarification_rounds"] == 2 and f["snapshot_id"] == "SNAP-0123456789ab"
    assert f["by_type"]["task_request"] == 5


def test_evidence_chain_resolves(store: LogStore) -> None:
    out = evidence_chain(load_view(store, INC), "HYP-PERF-000001-001")
    assert "hypothesis HYP-PERF-000001-001: link_congestion on SW_CAMPUS_4" in out
    assert "supports: observation OBS-PERF-000001-001" in out
    assert "observation OBS-PERF-000001-001: SW_CAMPUS_4 latency_ms = 180.0" in out
    assert "source records: REC-0001" in out and "data snapshot: SNAP-0123456789ab" in out
    assert "UNRESOLVED" not in out


def test_evidence_chain_reports_unresolved_references(tmp_path: Path) -> None:
    store = build_fixture_log(tmp_path / "u.sqlite3")
    view = load_view(store, INC)
    assert "UNRESOLVED: hypothesis HYP-NOPE-000001-001" in evidence_chain(
        view, "HYP-NOPE-000001-001"
    )
    # a hypothesis citing an observation that no message carries
    finding = json.loads(
        (KIT_DIR / "examples/valid/finding_with_not_assessable.json").read_text("utf-8")
    )
    finding["message_id"], finding["in_reply_to"] = f"{INC}-MSG-000060.R", f"{INC}-MSG-000060"
    finding["payload"]["hypotheses"][0] |= {
        "hypothesis_id": "HYP-PERF-000060-001",
        "supporting": [
            {
                "evidence_type": "observation",
                "evidence_id": "OBS-GONE-000001-001",
                "stance": "supports",
            }
        ],
    }
    store.append(raw_json=json.dumps(finding), header=finding, valid=True)
    out = evidence_chain(load_view(store, INC), "HYP-PERF-000060-001")
    assert "UNRESOLVED: observation OBS-GONE-000001-001 is not in this incident's messages" in out


def test_explain_shows_vocabulary_definitions(store: LogStore) -> None:
    out = explain_message(load_view(store, INC), f"{INC}-MSG-000001.R")
    assert '"message_type": "finding"' in out
    assert "Field meanings (from the controlled vocabularies):" in out
    assert re.search(
        r"metric = latency_ms\s+\(metric\): .+\[unit millisecond, category latency\]", out
    )
    assert re.search(r"not_assessable_reason = MISSING\s+\(not_assessable_reason\): \S", out)
    assert re.search(r"cause_type = link_congestion\s+\(cause_type\): \S", out)
    rejected = explain_message(load_view(store, INC), f"{INC}-MSG-000050")
    assert "REJECTED SENDER_NOT_AUTHORIZED" in rejected


def test_banner_always_present_and_no_forbidden_words(store: LogStore) -> None:
    view = load_view(store, INC)
    outputs = [
        render_table(view),
        render_table(view, show_rejected=True),
        render_sequence(view),
        render_json(view),
        evidence_chain(view, "HYP-PERF-000001-001"),
        evidence_chain(view, "HYP-NONE-000001-001"),
        explain_message(view, f"{INC}-MSG-000001.R"),
        explain_message(view, "nope"),
    ]
    for text in outputs:
        assert BANNER_TEXT in text
        assert not re.search(r"\blive\b|real-time", text, re.IGNORECASE)


def test_color_is_off_by_default(store: LogStore) -> None:
    view = load_view(store, INC)
    assert "\033[" not in render_table(view, show_rejected=True)
    assert "\033[31m" in render_table(view, show_rejected=True, color=True)


def test_cli(store: LogStore, tmp_path: Path) -> None:
    db = tmp_path / "cli.sqlite3"
    build_fixture_log(db)

    def run(*args: str) -> str:
        r = subprocess.run(
            [sys.executable, *args],
            capture_output=True,
            text=True,
            encoding="utf-8",
            cwd=REPO_ROOT,
            timeout=120,
            check=True,
        )
        return r.stdout

    table = run("-m", "netcoop.cli.trace", INC, "--db", str(db), "--show-rejected")
    assert table == render_table(load_view(store, INC), show_rejected=True)
    seq = run("-m", "netcoop.cli.main", "--db", str(db), "trace", INC, "--format", "sequence")
    assert BANNER_TEXT in seq and "orchestrator" in seq
    plain = run("-m", "netcoop.cli.main", "--db", str(db), "trace", INC)
    assert "[msg]" in plain and BANNER_TEXT not in plain  # original timeline unchanged
    ev = run("-m", "netcoop.cli.trace", INC, "--db", str(db), "--evidence", "HYP-PERF-000001-001")
    assert "source records: REC-0001" in ev

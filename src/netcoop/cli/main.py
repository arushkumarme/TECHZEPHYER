"""NetCoop AI command line (DLV-5). Simulation mode only; nothing here touches a network.

Examples::

    netcoop scenarios list
    netcoop run --scenario S-02 --trace
    netcoop run path/to/bundle.json --json-out report.json --md-out report.md --strict
    netcoop scenarios run-all --report var/scenario_results.md
    netcoop trace INC-0001
    netcoop validate-report report.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from netcoop.config.settings import load_settings
from netcoop.core.log_store import LogStore
from netcoop.orchestrator.faults import FAULTS
from netcoop.orchestrator.review import ReviewError, ReviewService
from netcoop.orchestrator.trace import render_trace
from netcoop.orchestrator.workflow import IncidentResult, Orchestrator
from netcoop.report.builder import strict_official
from netcoop.report.validate import validate_report
from netcoop.scenarios.generator import REPO_ROOT
from netcoop.scenarios.runner import (
    check_expectations,
    list_scenarios,
    load_scenario,
    run_scenario,
)

DEFAULT_DB = REPO_ROOT / "var" / "netcoop.sqlite3"
BANNER = "NetCoop AI - SIMULATED DATA - scenario playback (no access to any real network)"


def _faults(values: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for v in values:
        agent, _, fault = v.partition(":")
        if fault not in FAULTS:
            raise SystemExit(f"--inject-fault expects agent:{'|'.join(FAULTS)}, got {v!r}")
        out[agent] = fault
    return out


def _write(path: str | None, text: str) -> None:
    if path:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(text, encoding="utf-8", newline="\n")


def cmd_run(args: argparse.Namespace) -> int:
    store = LogStore(Path(args.db))
    settings = load_settings()
    faults = _faults(args.inject_fault or [])
    orch = Orchestrator(store, settings=settings, fault_injection=faults)
    if args.scenario:
        sc = load_scenario(args.scenario)
        orch.fault_injection = {**sc.meta.get("run", {}).get("fault_injection", {}), **faults}
        result = orch.run(
            sc.input_bytes, source=f"scenario:{sc.id}", label=sc.id, pause_after=args.pause_after
        )
    else:
        raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
        result = orch.run(raw, source="cli", label=args.input, pause_after=args.pause_after)
    return _emit(args, store, result)


def _emit(args: argparse.Namespace, store: LogStore, result: IncidentResult) -> int:
    print(BANNER, file=sys.stderr)
    if result.paused:
        print(
            f"incident {result.incident_id}: PAUSED in state {result.final_state} "
            f"(resume with: netcoop resume {result.incident_id})",
            file=sys.stderr,
        )
        return 0
    strict = getattr(args, "strict", False)
    report: dict[str, Any] = strict_official(result.report) if strict else result.report
    text = json.dumps(report, indent=2) + "\n"
    json_out = getattr(args, "json_out", None)
    _write(json_out, text)
    _write(getattr(args, "md_out", None), result.markdown)
    print(f"incident {result.incident_id}: final state {result.final_state}", file=sys.stderr)
    if getattr(args, "trace", False):
        print(render_trace(store, result.incident_id), file=sys.stderr)
    if not json_out:
        print(text, end="")
    return 0 if result.report.get("status") != "failed" else 2


def cmd_resume(args: argparse.Namespace) -> int:
    store = LogStore(Path(args.db))
    orch = Orchestrator(store, settings=load_settings())
    try:
        result = orch.resume(args.incident, pause_after=args.pause_after)
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return _emit(args, store, result)


def cmd_incidents(args: argparse.Namespace) -> int:
    store = LogStore(Path(args.db))
    orch = Orchestrator(store, settings=load_settings())
    resumable = set(orch.resumable())
    for inc in store.list_incidents():
        meta = store.incident_meta(inc) or {}
        state = orch.state_of(inc) or "-"
        label = meta.get("label") or meta.get("source", "")
        flag = "resumable" if inc in resumable else ""
        print(f"{inc}  {state:20} {label:30} {flag}")
    return 0


def cmd_scenarios(args: argparse.Namespace) -> int:
    ids = list_scenarios()
    if args.action == "list":
        for sid in ids:
            meta = load_scenario(sid).meta
            print(f"{sid:6} {meta['provenance']:42} {meta['title']}")
        return 0
    store = LogStore(Path(args.db))
    rows: list[tuple[str, str, str, str, list[str]]] = []
    confidence: dict[str, float] = {}
    for sid in ids:
        sc = load_scenario(sid)
        result = run_scenario(sc, store)
        confidence[sid] = result.report["confidence"]
        fails = check_expectations(result, sc.meta["expected"], reference_confidence=confidence)
        rows.append(
            (
                sid,
                result.incident_id,
                result.report["status"],
                result.report["netcoop_extensions"].get("top_cause_type", "-"),
                fails,
            )
        )
    lines = [
        f"# Scenario results ({BANNER})",
        "",
        "| Scenario | Incident | Status | Top cause | Result |",
        "|---|---|---|---|---|",
    ]
    for sid, inc, status, top, fails in rows:
        verdict = "PASS" if not fails else "FAIL: " + "; ".join(fails)
        lines.append(f"| {sid} | {inc} | {status} | {top} | {verdict} |")
    out = "\n".join(lines) + "\n"
    print(out)
    _write(args.report, out)
    return 0 if all(not f for *_, f in rows) else 1


def cmd_review(args: argparse.Namespace) -> int:
    svc = ReviewService(LogStore(Path(args.db)))
    try:
        items = svc.pending(args.incident)
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{args.incident}: state {svc.state(args.incident)} - every action is SIMULATED")
    for p in items:
        who = f" (by {p.reviewer})" if p.reviewer else ""
        print(f"[{p.index}] {p.approval_state}{who}: {p.action}")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    svc = ReviewService(LogStore(Path(args.db)))
    try:
        rec = svc.decide(
            args.incident, args.index, args.choice, reviewer=args.reviewer, note=args.note
        )
    except ReviewError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    print(f"{rec.decision}d [{rec.action_index}] by {rec.reviewer} at {rec.decided_at}")
    if rec.simulated_outcome:
        print(rec.simulated_outcome)
    print(f"incident state: {svc.state(args.incident)}")
    return 0


def cmd_community(args: argparse.Namespace) -> int:
    """Extension A from the command line (synthetic complaints only)."""
    from datetime import UTC, datetime

    from netcoop.community.pipeline import CommunityPipeline

    store = LogStore(Path(args.db))
    pipe = CommunityPipeline(store)
    if args.action == "submit":
        r = pipe.submit(
            args.text, channel="web_form", reporter=args.reporter, received_at=datetime.now(UTC)
        )
        print(json.dumps(r.__dict__, default=list))
        return 0 if r.accepted else 1
    if args.action == "load":
        data = json.loads(Path(args.text).read_text(encoding="utf-8"))
        for c in data["complaints"]:
            at = datetime.fromisoformat(c["received_at"].replace("Z", "+00:00"))
            r = pipe.submit(
                c["text"],
                channel=c.get("channel", "web_form"),
                reporter=c["reporter"],
                received_at=at,
            )
            print(
                f"{r.complaint_id}: accepted={r.accepted} duplicate={r.duplicate} "
                f"zone={r.zone} {r.reason or ''}"
            )
        print(json.dumps(pipe.stats()))
        return 0
    if args.action == "candidates":
        for c in pipe.candidates():
            print(
                f"{c.candidate_id} {c.zone} devices={c.entities} reporters="
                f"{c.distinct_reporters} complaints={c.complaint_count} {c.trust_label}"
            )
        return 0
    if args.action == "stats":
        print(json.dumps(pipe.stats()))
        return 0
    if not args.scenario:
        print("error: investigate needs --scenario", file=sys.stderr)
        return 1
    try:
        result = pipe.investigate(
            args.text,
            Orchestrator(store, settings=load_settings()),
            load_scenario(args.scenario).input_bytes,
        )
    except KeyError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    return _emit(args, store, result)


def cmd_trace(args: argparse.Namespace) -> int:
    print(render_trace(LogStore(Path(args.db)), args.incident), end="")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    report = json.loads(Path(args.report).read_text(encoding="utf-8"))
    errors = validate_report(
        report,
        observation_ids={
            t["observation_id"]
            for t in report.get("netcoop_extensions", {}).get("evidence_trace", [])
        },
        finding_agents=set(report.get("evidence_sources", [])),
        strict="netcoop_extensions" not in report,
    )
    for e in errors:
        print(f"INVALID: {e}")
    if not errors:
        print("valid")
    return 1 if errors else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="netcoop", description=BANNER)
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite log (default var/)")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="diagnose one telemetry bundle")
    src = r.add_mutually_exclusive_group(required=True)
    src.add_argument("input", nargs="?", help="bundle JSON file, or - for stdin")
    src.add_argument("--scenario", help="scenario id, e.g. S-02")
    r.add_argument("--json-out")
    r.add_argument("--md-out")
    r.add_argument("--strict", action="store_true", help="only the ten official keys")
    r.add_argument("--trace", action="store_true", help="print the message/state trace")
    r.add_argument(
        "--inject-fault",
        action="append",
        metavar="AGENT:FAULT",
        help=f"simulate an agent fault ({', '.join(FAULTS)})",
    )
    r.add_argument(
        "--pause-after", metavar="STATE", help="stop once the incident enters STATE; resume later"
    )
    r.set_defaults(func=cmd_run)

    rs = sub.add_parser("resume", help="continue a paused or interrupted incident")
    rs.add_argument("incident")
    rs.add_argument("--pause-after", metavar="STATE")
    rs.add_argument("--json-out")
    rs.add_argument("--md-out")
    rs.add_argument("--strict", action="store_true")
    rs.add_argument("--trace", action="store_true")
    rs.set_defaults(func=cmd_resume)

    inc = sub.add_parser("incidents", help="list incidents with their current state")
    inc.set_defaults(func=cmd_incidents)

    cm = sub.add_parser("community", help="Extension A: synthetic complaints")
    cm.add_argument("action", choices=["submit", "load", "candidates", "stats", "investigate"])
    cm.add_argument(
        "text",
        nargs="?",
        default="",
        help="complaint text (submit), JSON file (load) or candidate id (investigate)",
    )
    cm.add_argument("--reporter", default="cli-test-reporter")
    cm.add_argument("--scenario", help="telemetry scenario to investigate against")
    cm.set_defaults(func=cmd_community)

    rv = sub.add_parser("review", help="list an incident's recommendations and decisions")
    rv.add_argument("incident")
    rv.set_defaults(func=cmd_review)
    for name, choice in (("approve", "approve"), ("reject", "reject")):
        d = sub.add_parser(name, help=f"{name} one recommendation (outcome is simulated)")
        d.add_argument("incident")
        d.add_argument("index", type=int)
        d.add_argument("--reviewer", required=True, help="who decides (recorded)")
        d.add_argument("--note", default="")
        d.set_defaults(func=cmd_decide, choice=choice)

    s = sub.add_parser("scenarios", help="list or run the scenario suite")
    s.add_argument("action", choices=["list", "run-all"])
    s.add_argument("--report", help="write a Markdown results table")
    s.set_defaults(func=cmd_scenarios)

    t = sub.add_parser("trace", help="print an incident's trace from the log")
    t.add_argument("incident")
    t.set_defaults(func=cmd_trace)

    v = sub.add_parser("validate-report", help="check a report JSON against doc 07 §8")
    v.add_argument("report")
    v.set_defaults(func=cmd_validate)

    ck = sub.add_parser("conformance", help="run the protocol conformance kit")
    ck.set_defaults(func=lambda a: _conformance_main([]))
    vm = sub.add_parser("validate", help="check one protocol message or conversation file")
    vm.add_argument("file")
    vm.add_argument("--max-bytes", type=int, default=None)
    vm.set_defaults(
        func=lambda a: _validate_main(
            [a.file, *(["--max-bytes", str(a.max_bytes)] if a.max_bytes else [])]
        )
    )
    return p


def _conformance_main(argv: list[str]) -> int:
    from netcoop.cli.conformance import main as run

    return run(argv)


def _validate_main(argv: list[str]) -> int:
    from netcoop.cli.validate import main as run

    return run(argv)


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if load_settings().mode != "simulation":  # pragma: no cover - settings refuse it anyway
        raise SystemExit("only simulation mode exists")
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

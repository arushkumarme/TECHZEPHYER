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
from netcoop.orchestrator.trace import render_trace
from netcoop.orchestrator.workflow import Orchestrator
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
    if args.scenario:
        result = run_scenario(
            load_scenario(args.scenario), store, settings=settings, extra_faults=faults
        )
    else:
        raw = sys.stdin.buffer.read() if args.input == "-" else Path(args.input).read_bytes()
        result = Orchestrator(store, settings=settings, fault_injection=faults).run(
            raw, source="cli", label=args.input
        )
    report: dict[str, Any] = strict_official(result.report) if args.strict else result.report
    text = json.dumps(report, indent=2) + "\n"
    _write(args.json_out, text)
    _write(args.md_out, result.markdown)
    print(BANNER, file=sys.stderr)
    print(f"incident {result.incident_id}: final state {result.final_state}", file=sys.stderr)
    if args.trace:
        print(render_trace(store, result.incident_id), file=sys.stderr)
    if not args.json_out:
        print(text, end="")
    return 0 if result.report["status"] != "failed" else 2


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
    r.set_defaults(func=cmd_run)

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
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if load_settings().mode != "simulation":  # pragma: no cover - settings refuse it anyway
        raise SystemExit("only simulation mode exists")
    code: int = args.func(args)
    return code


if __name__ == "__main__":
    raise SystemExit(main())

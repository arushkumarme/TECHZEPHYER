"""Protocol inspector: an incident's conversation from the message log.

    uv run python -m netcoop.cli.trace INC-0001 [--db PATH] [--format table|sequence|json]
        [--show-rejected] [--type TYPE] [--sender NAME] [--color | --no-color]
    uv run python -m netcoop.cli.trace INC-0001 --evidence HYP-PERF-000003-001
    uv run python -m netcoop.cli.trace INC-0001 --explain INC-0001-MSG-000003.R

(``netcoop trace INC-0001`` keeps its original state+message timeline; the same flags
switch it to the inspector.)
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netcoop.core.inspector import (
    evidence_chain,
    explain_message,
    load_view,
    render_json,
    render_sequence,
    render_table,
)
from netcoop.core.log_store import LogStore
from netcoop.scenarios.generator import REPO_ROOT

DEFAULT_DB = REPO_ROOT / "var" / "netcoop.sqlite3"


def add_arguments(p: argparse.ArgumentParser, *, with_incident: bool = True) -> None:
    if with_incident:
        p.add_argument("incident")
    p.add_argument("--format", choices=["table", "sequence", "json"], default=None)
    p.add_argument("--show-rejected", action="store_true", help="include rejected messages")
    p.add_argument("--type", action="append", dest="types", help="only this message type")
    p.add_argument("--sender", help="only messages from this participant")
    p.add_argument("--evidence", metavar="HYP-ID", help="print a hypothesis's evidence")
    p.add_argument("--explain", metavar="MSG-ID", help="explain one message's fields")
    color = p.add_mutually_exclusive_group()
    color.add_argument("--color", dest="color", action="store_true", help="ANSI colour")
    color.add_argument("--no-color", dest="color", action="store_false", help="(default)")
    p.set_defaults(color=False)


def wants_inspector(args: argparse.Namespace) -> bool:
    return bool(
        args.format
        or args.evidence
        or args.explain
        or args.show_rejected
        or args.types
        or args.sender
    )


def render(args: argparse.Namespace, store: LogStore) -> str:
    view = load_view(store, args.incident)
    if args.evidence:
        return evidence_chain(view, args.evidence)
    if args.explain:
        return explain_message(view, args.explain)
    filters = {
        "show_rejected": args.show_rejected,
        "types": set(args.types) if args.types else None,
        "sender": args.sender,
    }
    if args.format == "json":
        return render_json(view, **filters)
    if args.format == "sequence":
        return render_sequence(view, color=args.color, **filters)
    return render_table(view, color=args.color, **filters)


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(
        prog="python -m netcoop.cli.trace",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--db", default=str(DEFAULT_DB), help="SQLite log (default var/)")
    add_arguments(p)
    args = p.parse_args(argv)
    print(render(args, LogStore(Path(args.db))), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

"""Check one message or conversation file against the protocol.

    uv run python -m netcoop.cli.validate FILE [--max-bytes N]   (or: netcoop validate FILE)

A file with a "steps" list is a conversation (each step: incident_state + message); any
other JSON object is a single message. Exit 0 if accepted, 1 if rejected.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from netcoop.conformance import check_file
from netcoop.core.parse import DEFAULT_MAX_MESSAGE_BYTES


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    p = argparse.ArgumentParser(prog="netcoop validate", description=__doc__)
    p.add_argument("file", type=Path)
    p.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_MESSAGE_BYTES)
    args = p.parse_args(argv)
    outcome = check_file(args.file, max_bytes=args.max_bytes)
    if outcome.verdict == "accepted":
        what = "conversation" if outcome.messages_checked > 1 else "message"
        print(
            f"ACCEPTED: {args.file.name} is a valid {what} "
            f"({outcome.messages_checked} message(s) checked)."
        )
        for w in outcome.warnings:
            print(f"  warning: {w}")
        return 0
    where = f" at message #{outcome.failing_index}" if outcome.failing_index is not None else ""
    print(f"REJECTED{where} ({outcome.code}):")
    for reason in outcome.reasons:
        print(f"  - {reason}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

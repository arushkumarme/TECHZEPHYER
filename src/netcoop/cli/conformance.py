"""Run the protocol conformance kit.

    uv run python -m netcoop.cli.conformance      (or: uv run netcoop conformance)

Every example in conformance/manifest.json goes through the REAL parser and conversation
guard. Prints a short summary with the plain-English reason for each rejection; exits 1 if
anything differs from the manifest.
"""

from __future__ import annotations

import sys

from netcoop.conformance import render_summary, run_manifest


def main(argv: list[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    results = run_manifest()
    print(render_summary(results), end="")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

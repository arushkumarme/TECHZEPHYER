"""Regenerate the GENERATED blocks in the docs and the vocabulary JSON export.

    uv run python scripts/generate_docs.py           # write
    uv run python scripts/generate_docs.py --check   # exit 1 if anything is stale

Idempotent: running it twice produces no diff. Blocks live between
``<!-- BEGIN GENERATED: <name> -->`` and ``<!-- END GENERATED: <name> -->`` markers.
"""

from __future__ import annotations

import sys
from pathlib import Path

from netcoop.core.vocabulary.render import (
    APPENDIX_BEGIN,
    APPENDIX_END,
    render_appendix,
    render_json,
)
from netcoop.scenarios.generator import REPO_ROOT

DOC05 = REPO_ROOT / "docs" / "05-protocol-spec.md"
VOCAB_JSON = REPO_ROOT / "conformance" / "vocabularies.json"
APPENDIX_HEADING = "## Appendix A: Controlled vocabularies"


def updated_doc05(text: str) -> str:
    block = render_appendix()
    if APPENDIX_BEGIN in text and APPENDIX_END in text:
        start = text.index(APPENDIX_BEGIN)
        end = text.index(APPENDIX_END) + len(APPENDIX_END)
        return text[:start] + block + text[end:]
    return text.rstrip("\n") + f"\n\n{APPENDIX_HEADING}\n\n{block}\n"


def main(argv: list[str]) -> int:
    check = "--check" in argv
    targets: list[tuple[Path, str]] = [
        (DOC05, updated_doc05(DOC05.read_text(encoding="utf-8"))),
        (VOCAB_JSON, render_json()),
    ]
    stale = []
    for path, content in targets:
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != content:
            stale.append(path.relative_to(REPO_ROOT))
            if not check:
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(content, encoding="utf-8", newline="\n")
    if check and stale:
        print("stale generated content (run scripts/generate_docs.py):", *stale, sep="\n  ")
        return 1
    print("up to date" if not stale else f"regenerated: {', '.join(map(str, stale))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))

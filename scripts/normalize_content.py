#!/usr/bin/env python3
"""
Normalize conversion artifacts already present under content/.

Primary path: the same logic now runs automatically inside
convert_incoming_pdfs.py on every new file written to content/.
This script remains for:
  - one-shot cleanup of files that already exist
  - manual / ad-hoc runs

What it does:
  - Map private-use glyph U+100170 → 年
  - Normalize non-standard brackets: ‹› → 〈〉, «» → 《》
  - Strip residual mid-paragraph 公报 running-header fragments

Usage:
  python scripts/normalize_content.py          # dry-run report
  python scripts/normalize_content.py --write  # apply in place
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

CONTENT_ROOT = Path("content")

_GLYPH_MAP = str.maketrans({
    "\U00100170": "\u5e74",  # ခ70 → 年
})

_BRACKET_MAP = str.maketrans({
    "\u2039": "\u3008",  # ‹ → 〈
    "\u203a": "\u3009",  # › → 〉
    "\u00ab": "\u300a",  # « → 《
    "\u00bb": "\u300b",  # » → 》
})

_ARTIFACT_MAP = str.maketrans({**_GLYPH_MAP, **_BRACKET_MAP})

_HEADER_FRAG = re.compile(
    r"全国人民代表大会常务委员会公报\d{4}年\d+"
)


def normalize(text: str) -> str:
    text = text.translate(_ARTIFACT_MAP)
    text = _HEADER_FRAG.sub("", text)
    text = re.sub(r" {2,}", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--write", action="store_true", help="write changes back to disk")
    args = ap.parse_args()

    changed_files = 0
    total_repl = 0

    for path in sorted(CONTENT_ROOT.rglob("*.md")):
        raw = path.read_text(encoding="utf-8")
        fixed = normalize(raw)
        if fixed == raw:
            continue

        n = sum(1 for a, b in zip(raw, fixed) if a != b) + abs(len(fixed) - len(raw))
        print(f"{path.relative_to(CONTENT_ROOT)}  (~{n} changes)")
        changed_files += 1
        total_repl += n

        if args.write:
            path.write_text(fixed, encoding="utf-8")

    print(f"\n{'Wrote' if args.write else 'Would write'} {changed_files} file(s), ~{total_repl} changes")
    if not args.write and changed_files:
        print("Re-run with --write to apply.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

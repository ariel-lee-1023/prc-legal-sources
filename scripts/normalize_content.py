#!/usr/bin/env python3
"""
One-time normalization of conversion artifacts in content/.

- Map stray private-use glyphs (U+100170 → 年) that appear as residual
  running headers from certain 公报 PDFs.
- Normalize non-standard title brackets:
    ‹ → 〈   › → 〉
    « → 《   » → 》
- After mapping, strip residual mid-paragraph running-header fragments
  of the form "全国人民代表大会常务委员会公报YYYY年N".

This closes the small accuracy gap in the authoritative texts that an
IP-aware reader would notice first (esp. 著作权法 header).

Usage:
  python scripts/normalize_content.py          # dry-run report
  python scripts/normalize_content.py --write  # apply in place
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

CONTENT_ROOT = Path("content")

# Private-use / conversion artifacts observed in the 公报 text-layer
# (U+100170 is the stand-in for 年 in "2021ခ701" headers).
GLYPH_MAP = str.maketrans({
    "\U00100170": "\u5e74",  # ခ70 → 年
})

BRACKET_MAP = str.maketrans({
    "\u2039": "\u3008",  # ‹ → 〈
    "\u203a": "\u3009",  # › → 〉
    "\u00ab": "\u300a",  # « → 《
    "\u00bb": "\u300b",  # » → 》
})

FULL_MAP = str.maketrans({**GLYPH_MAP, **BRACKET_MAP})

# After glyph map, residual headers look like this (may be glued to text).
HEADER_FRAG = re.compile(
    r"全国人民代表大会常务委员会公报\d{4}年\d+"
)


def normalize(text: str) -> str:
    text = text.translate(FULL_MAP)
    # Remove residual running-header fragments that survived the original
    # conversion (they were invisible to the old regex because of the PUA glyph).
    text = HEADER_FRAG.sub("", text)
    # Collapse any double spaces or awkward joins created by the strip
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

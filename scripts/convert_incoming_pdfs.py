#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into Markdown under content/.

Directory mapping (strict, effect hierarchy):

  incoming/01_Constitution/*.pdf
      → content/01_Constitution/<name>.md
  incoming/02_Statutes/*.pdf
      → content/02_Statutes/<name>.md
  incoming/03_Administrative_Regulations/*.pdf
      → content/03_Administrative_Regulations/<name>.md
  incoming/04_Local_Regulations/*.pdf
      → content/04_Local_Regulations/<name>.md
  incoming/05_Rules/*.pdf
      → content/05_Rules/<name>.md
  incoming/06_Judicial_Interpretations/*.pdf
      → content/06_Judicial_Interpretations/<name>.md
  incoming/07_Authoritative_Cases/*.pdf
      → content/07_Authoritative_Cases/<name>.md
  incoming/08_Judicial_Guidance_Documents/*.pdf
      → content/08_Judicial_Guidance_Documents/<name>.md
  incoming/09_Local_Judicial_Guidance/*.pdf
      → content/09_Local_Judicial_Guidance/<name>.md
  incoming/10_Other_Authoritative_Materials/*.pdf
      → content/10_Other_Authoritative_Materials/<name>.md

After successful conversion the source PDF is deleted (keeps the repo light).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

from markitdown import MarkItDown

INCOMING_ROOT = Path("incoming")
CONTENT_ROOT = Path("content")

# Order = legal effect hierarchy (top → bottom)
SUBFOLDERS = [
    "01_Constitution",                    # 宪法 — supreme, unconditioned
    "02_Statutes",                        # 法律 — NPC / NPCSC
    "03_Administrative_Regulations",      # 行政法规 — State Council
    "04_Local_Regulations",               # 地方性法规
    "05_Rules",                           # 规章 — department / local government rules
    "06_Judicial_Interpretations",        # 司法解释 — distinct effect-tier
    "07_Authoritative_Cases",             # 指导性案例 / 权威案例 — interpretive
    "08_Judicial_Guidance_Documents",     # 司法指导性文件
    "09_Local_Judicial_Guidance",         # 地方司法指导文件
    "10_Other_Authoritative_Materials",   # 其他权威材料
]


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
    """Convert a single PDF. Returns True if a new/changed .md was written."""
    md = MarkItDown()
    try:
        result = md.convert(str(pdf_path))
        text = (result.text_content or "").strip()
    except Exception as e:
        print(f"  CONVERT FAIL {pdf_path.name}: {e}")
        return False

    if not text:
        print(f"  EMPTY      {pdf_path.name}")
        return False

    base = safe_name(pdf_path.stem)
    out_path = out_dir / f"{base}.md"

    header = (
        f"# {pdf_path.stem}\n\n"
        f"> original PDF: `{pdf_path.name}`  \n"
        f"> folder: `{out_dir.name}`  \n"
        f"> converted with markitdown\n\n"
    )
    full = header + text

    if out_path.exists():
        existing = out_path.read_text(encoding="utf-8")
        if content_hash(existing) == content_hash(full):
            print(f"  SKIP (unchanged) {out_path}")
            pdf_path.unlink(missing_ok=True)
            return False

    out_dir.mkdir(parents=True, exist_ok=True)
    out_path.write_text(full, encoding="utf-8")
    print(f"  WROTE     {out_path}")

    pdf_path.unlink(missing_ok=True)
    print(f"  DELETED   {pdf_path}")
    return True


def main() -> int:
    changed = 0
    total_pdfs = 0

    for sub in SUBFOLDERS:
        src_dir = INCOMING_ROOT / sub
        if not src_dir.is_dir():
            print(f"(no folder) {src_dir}")
            continue

        pdfs = sorted(src_dir.glob("*.pdf")) + sorted(src_dir.glob("*.PDF"))
        if not pdfs:
            print(f"(empty)    {src_dir}")
            continue

        print(f"\n=== {sub} ({len(pdfs)} PDF(s)) ===")
        out_dir = CONTENT_ROOT / sub

        for pdf in pdfs:
            total_pdfs += 1
            if convert_one(pdf, out_dir):
                changed += 1

    print(f"\nDone. scanned={total_pdfs}  written/updated={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

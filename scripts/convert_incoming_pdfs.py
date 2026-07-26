#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into Markdown under content/.

Primary extractor: PyMuPDF (fitz) — better Chinese + multi-column handling.
Fallback: markitdown/pdfminer if PyMuPDF fails.

After successful conversion the source PDF is deleted (keeps the repo light).
"""

from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

INCOMING_ROOT = Path("incoming")
CONTENT_ROOT = Path("content")

SUBFOLDERS = [
    "01_Constitution",
    "02_Statutes",
    "03_Administrative_Regulations",
    "04_Local_Regulations",
    "05_Rules",
    "06_Judicial_Interpretations",
    "07_Authoritative_Cases",
    "08_Judicial_Guidance_Documents",
    "09_Local_Judicial_Guidance",
    "10_Other_Authoritative_Materials",
]

# Fullwidth ASCII → halfwidth (gazette PDFs often use fullwidth digits)
_FW_TRANS = str.maketrans(
    {
        **{ord(f"０") + i: ord("0") + i for i in range(10)},
        **{ord(f"Ａ") + i: ord("A") + i for i in range(26)},
        **{ord(f"ａ") + i: ord("a") + i for i in range(26)},
        ord("　"): " ",
        ord("（"): "(",
        ord("）"): ")",
        ord("，"): "，",  # keep Chinese comma
        ord("："): "：",
        ord("；"): "；",
    }
)

# Common running headers / footers from 公报
_HEADER_RE = re.compile(
    r"^\s*全国人民代表大会常务委员会公报[\d０-９·\.\s]+\s*$",
    re.MULTILINE,
)
_PAGE_NUM_RE = re.compile(r"^\s*[—\-–]\s*[\d０-９]+\s*[—\-–]\s*$", re.MULTILINE)


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cleanup_text(text: str) -> str:
    """Normalize fullwidth digits and strip gazette headers/footers."""
    text = text.translate(_FW_TRANS)
    text = _HEADER_RE.sub("", text)
    text = _PAGE_NUM_RE.sub("", text)
    # collapse 3+ blank lines → 2
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_with_pymupdf(pdf_path: Path) -> str | None:
    try:
        import fitz  # PyMuPDF
    except ImportError:
        return None

    try:
        doc = fitz.open(pdf_path)
        parts: list[str] = []
        for page in doc:
            # "text" with sort=True improves reading order on multi-column pages
            t = page.get_text("text", sort=True) or ""
            if t.strip():
                parts.append(t.strip())
        doc.close()
        raw = "\n\n".join(parts).strip()
        return raw or None
    except Exception as e:
        print(f"  pymupdf fail {pdf_path.name}: {e}")
        return None


def extract_with_markitdown(pdf_path: Path) -> str | None:
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(pdf_path))
        text = (result.text_content or "").strip()
        return text or None
    except Exception as e:
        print(f"  markitdown fail {pdf_path.name}: {e}")
        return None


def extract_text(pdf_path: Path) -> str | None:
    text = extract_with_pymupdf(pdf_path)
    engine = "pymupdf"
    if not text:
        text = extract_with_markitdown(pdf_path)
        engine = "markitdown"
    if not text:
        return None
    print(f"  engine={engine}")
    return cleanup_text(text)


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
    text = extract_text(pdf_path)
    if not text:
        print(f"  EMPTY/FAIL {pdf_path.name}")
        return False

    # Heuristic: if almost no CJK, warn (likely still broken)
    cjk = len(re.findall(r"[\u4e00-\u9fff]", text))
    if cjk < 20 and len(text) > 100:
        print(f"  WARN low CJK count={cjk} for {pdf_path.name}")

    base = safe_name(pdf_path.stem)
    out_path = out_dir / f"{base}.md"

    header = (
        f"# {pdf_path.stem}\n\n"
        f"> original PDF: `{pdf_path.name}`  \n"
        f"> folder: `{out_dir.name}`  \n"
        f"> converted with pymupdf/markitdown\n\n"
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
    print(f"  WROTE     {out_path}  ({len(text)} chars, cjk={cjk})")

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

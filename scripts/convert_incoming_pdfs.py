#!/usr/bin/env python3
"""
Convert PDFs dropped into incoming/ into Markdown under content/.

Extraction strategy (per page):
  1. Text layer present  → PyMuPDF, dual-column aware when needed
  2. Image-only / scanned → Tesseract Chinese OCR (chi_sim), two-column split
  3. Fallback            → markitdown/pdfminer

Post-process:
  - fullwidth → halfwidth digits/letters
  - strip 公报 running headers / page numbers
  - join soft line-wraps from justified Chinese typesetting

After successful conversion the source PDF is deleted (keeps the repo light).
"""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
import tempfile
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

MIN_CJK_PAGE = 8
MIN_CJK_DOC = 30

OCR_DPI = 280
OCR_LANG = "chi_sim+eng"

_FW_TRANS = str.maketrans(
    {
        **{ord("０") + i: ord("0") + i for i in range(10)},
        **{ord("Ａ") + i: ord("A") + i for i in range(26)},
        **{ord("ａ") + i: ord("a") + i for i in range(26)},
        ord("　"): " ",
        ord("（"): "(",
        ord("）"): ")",
    }
)

_HEADER_RE = re.compile(
    r"^\s*全国人民代表大会常务委员会公报[\d０-９·\.\s]+\s*$",
    re.MULTILINE,
)
_PAGE_NUM_RE = re.compile(
    r"^\s*[—\-–]\s*[\d０-９]+\s*[—\-–]\s*$",
    re.MULTILINE,
)
_STRUCT_START = re.compile(
    r"^(第[一二三四五六七八九十百千零〇\d]+[编章节条分节]"
    r"|[（(][一二三四五六七八九十\d]+[)）]"
    r"|\d+[、.]\s"
    r"|附\s*则"
    r"|[一二三四五六七八九十]+、)"
)
_SENT_END = set("。！？；：”』」）】》…")


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def cjk_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text))


def join_soft_wraps(text: str) -> str:
    """Re-join lines broken by PDF justified layout mid-sentence.

    Handles both single newlines and blank-line gaps that extractors
    insert between consecutive visual lines of the same paragraph.
    """
    lines = [ln.rstrip() for ln in text.split("\n")]
    out: list[str] = []
    buf = ""

    def flush() -> None:
        nonlocal buf
        if buf:
            out.append(buf)
            buf = ""

    i = 0
    n = len(lines)
    while i < n:
        stripped = lines[i].strip()

        if not stripped:
            j = i + 1
            while j < n and not lines[j].strip():
                j += 1
            if buf and j < n:
                nxt = lines[j].strip()
                if (
                    buf[-1] not in _SENT_END
                    and not _STRUCT_START.match(nxt)
                    and not _PAGE_NUM_RE.match(nxt)
                ):
                    i += 1
                    continue
            flush()
            if out and out[-1] != "":
                out.append("")
            i += 1
            continue

        if _PAGE_NUM_RE.match(stripped) or _HEADER_RE.match(stripped):
            i += 1
            continue

        if _STRUCT_START.match(stripped):
            flush()
            buf = stripped
            i += 1
            continue

        if not buf:
            buf = stripped
            i += 1
            continue

        if buf[-1] in _SENT_END:
            flush()
            buf = stripped
            i += 1
            continue

        buf = buf + stripped
        i += 1

    flush()
    result = re.sub(r"\n{3,}", "\n\n", "\n".join(out))
    return result.strip()


def cleanup_text(text: str) -> str:
    text = text.translate(_FW_TRANS)
    text = _HEADER_RE.sub("", text)
    text = _PAGE_NUM_RE.sub("", text)
    text = join_soft_wraps(text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _blocks_to_columns(page) -> str:
    """Extract blocks; dual-column only when layout is clearly two columns.

    PyMuPDF blocks tuple: (x0, y0, x1, y1, text, block_no, block_type)
    block_type 0 = text, 1 = image.

    Guard: any full-width line (width > 60% of page) forces single-column
    reading order, so official single-column statutes are never scrambled.
    """
    blocks = page.get_text("blocks", sort=True) or []
    text_blocks = []
    for b in blocks:
        if len(b) < 7:
            continue
        x0, y0, x1, y1, txt, _bno, btype = (
            b[0], b[1], b[2], b[3], b[4], b[5], b[6]
        )
        if btype != 0:
            continue
        if not (txt or "").strip():
            continue
        cleaned = re.sub(r"\s*\n\s*", "", txt.strip())
        text_blocks.append((x0, y0, x1, y1, cleaned))

    if not text_blocks:
        return ""

    page_w = float(page.rect.width)

    # Full-width lines ⇒ single column (official statute layout)
    if any((b[2] - b[0]) > page_w * 0.60 for b in text_blocks):
        text_blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
        return "\n".join(b[4] for b in text_blocks)

    # True dual-column: blocks wholly on left vs wholly on right of gutter
    left = [b for b in text_blocks if b[2] < page_w * 0.52]
    right = [b for b in text_blocks if b[0] > page_w * 0.48]
    left_cjk = sum(cjk_count(b[4]) for b in left)
    right_cjk = sum(cjk_count(b[4]) for b in right)
    dual = (
        left_cjk >= MIN_CJK_PAGE
        and right_cjk >= MIN_CJK_PAGE
        and min(left_cjk, right_cjk) / max(left_cjk, right_cjk) > 0.25
    )

    if dual:
        left.sort(key=lambda b: (round(b[1], 1), b[0]))
        right.sort(key=lambda b: (round(b[1], 1), b[0]))
        parts = [b[4] for b in left] + [""] + [b[4] for b in right]
        return "\n".join(parts)

    text_blocks.sort(key=lambda b: (round(b[1], 1), b[0]))
    return "\n".join(b[4] for b in text_blocks)


def extract_text_layer(pdf_path: Path) -> tuple[str | None, str]:
    try:
        import fitz
    except ImportError:
        return None, "no-fitz"

    try:
        doc = fitz.open(pdf_path)
        parts: list[str] = []
        for page in doc:
            t = _blocks_to_columns(page)
            if not t.strip():
                t = page.get_text("text", sort=True) or ""
            if t.strip():
                parts.append(t.strip())
        doc.close()
        raw = "\n\n".join(parts).strip()
        if cjk_count(raw) < MIN_CJK_DOC:
            return None, f"text-layer-low-cjk={cjk_count(raw)}"
        return raw, "text-layer"
    except Exception as e:
        print(f"  text-layer fail {pdf_path.name}: {e}")
        return None, f"text-layer-error:{e}"


def _tesseract_available() -> bool:
    try:
        r = subprocess.run(
            ["tesseract", "--list-langs"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        langs = (r.stdout or "") + (r.stderr or "")
        return "chi_sim" in langs
    except Exception:
        return False


def _ocr_clip_tesseract(page, clip, dpi: int, tmpdir: Path) -> str:
    import fitz

    mat = fitz.Matrix(dpi / 72.0, dpi / 72.0)
    pix = page.get_pixmap(matrix=mat, clip=clip, colorspace=fitz.csGRAY)
    img_path = tmpdir / f"clip_{int(clip.x0)}_{int(clip.y0)}.png"
    pix.save(str(img_path))
    out_base = tmpdir / f"out_{int(clip.x0)}_{int(clip.y0)}"
    cmd = [
        "tesseract",
        str(img_path),
        str(out_base),
        "-l",
        OCR_LANG,
        "--psm",
        "6",
        "-c",
        "preserve_interword_spaces=1",
    ]
    subprocess.run(cmd, capture_output=True, timeout=180)
    txt_path = Path(str(out_base) + ".txt")
    if not txt_path.exists():
        return ""
    return txt_path.read_text(encoding="utf-8", errors="ignore").strip()


def ocr_page_two_column(page, dpi: int = OCR_DPI) -> str:
    import fitz

    w, h = float(page.rect.width), float(page.rect.height)
    left_clip = fitz.Rect(0, 0, w * 0.52, h)
    right_clip = fitz.Rect(w * 0.48, 0, w, h)

    with tempfile.TemporaryDirectory(prefix="prc_ocr_") as td:
        tmp = Path(td)
        left = _ocr_clip_tesseract(page, left_clip, dpi, tmp)
        right = _ocr_clip_tesseract(page, right_clip, dpi, tmp)
    parts = [p for p in (left, right) if p]
    return "\n\n".join(parts)


def ocr_page_full(page, dpi: int = OCR_DPI) -> str:
    try:
        tp = page.get_textpage_ocr(language=OCR_LANG, dpi=dpi, full=True)
        return (page.get_text("text", textpage=tp, sort=True) or "").strip()
    except Exception as e:
        print(f"  textpage_ocr fail: {e}")
        return ""


def extract_with_ocr(pdf_path: Path) -> tuple[str | None, str]:
    if not _tesseract_available():
        print("  OCR skipped: tesseract chi_sim not available")
        return None, "ocr-unavailable"

    try:
        import fitz
    except ImportError:
        return None, "no-fitz"

    try:
        doc = fitz.open(pdf_path)
        parts: list[str] = []
        n = doc.page_count
        print(f"  OCR pages={n} dpi={OCR_DPI} lang={OCR_LANG}")
        for i, page in enumerate(doc):
            t = ocr_page_two_column(page)
            if cjk_count(t) < MIN_CJK_PAGE:
                t2 = ocr_page_full(page)
                if cjk_count(t2) > cjk_count(t):
                    t = t2
            if t.strip():
                parts.append(t.strip())
            if (i + 1) % 5 == 0 or i + 1 == n:
                print(f"    ocr progress {i + 1}/{n}")
        doc.close()
        raw = "\n\n".join(parts).strip()
        if cjk_count(raw) < MIN_CJK_DOC:
            return None, f"ocr-low-cjk={cjk_count(raw)}"
        return raw, "ocr"
    except Exception as e:
        print(f"  OCR fail {pdf_path.name}: {e}")
        return None, f"ocr-error:{e}"


def extract_with_markitdown(pdf_path: Path) -> tuple[str | None, str]:
    try:
        from markitdown import MarkItDown

        md = MarkItDown()
        result = md.convert(str(pdf_path))
        text = (result.text_content or "").strip()
        if cjk_count(text) < MIN_CJK_DOC:
            return None, f"markitdown-low-cjk={cjk_count(text)}"
        return text, "markitdown"
    except Exception as e:
        print(f"  markitdown fail {pdf_path.name}: {e}")
        return None, f"markitdown-error:{e}"


def extract_text(pdf_path: Path) -> tuple[str | None, str]:
    text, note = extract_text_layer(pdf_path)
    if text:
        print(f"  engine=text-layer ({note})")
        return cleanup_text(text), "text-layer"

    print(f"  text-layer insufficient ({note}), trying OCR…")
    text, note = extract_with_ocr(pdf_path)
    if text:
        print(f"  engine=ocr ({note})")
        return cleanup_text(text), "ocr"

    print(f"  OCR insufficient ({note}), trying markitdown…")
    text, note = extract_with_markitdown(pdf_path)
    if text:
        print(f"  engine=markitdown ({note})")
        return cleanup_text(text), "markitdown"

    return None, note


def convert_one(pdf_path: Path, out_dir: Path) -> bool:
    text, engine = extract_text(pdf_path)
    if not text:
        print(f"  EMPTY/FAIL {pdf_path.name} ({engine})")
        return False

    cjk = cjk_count(text)
    if cjk < MIN_CJK_DOC:
        print(f"  WARN low CJK count={cjk} for {pdf_path.name}")

    base = safe_name(pdf_path.stem)
    out_path = out_dir / f"{base}.md"

    header = (
        f"# {pdf_path.stem}\n\n"
        f"> original PDF: `{pdf_path.name}`  \n"
        f"> folder: `{out_dir.name}`  \n"
        f"> engine: `{engine}`\n\n"
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
    print(f"  WROTE     {out_path}  ({len(text)} chars, cjk={cjk}, engine={engine})")

    pdf_path.unlink(missing_ok=True)
    print(f"  DELETED   {pdf_path}")
    return True


def main() -> int:
    changed = 0
    total_pdfs = 0

    tess_ok = _tesseract_available()
    print(f"tesseract chi_sim available: {tess_ok}")

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
            print(f"\n--- {pdf.name} ---")
            if convert_one(pdf, out_dir):
                changed += 1

    print(f"\nDone. scanned={total_pdfs}  written/updated={changed}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

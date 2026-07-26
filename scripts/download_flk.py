#!/usr/bin/env python3
"""
Incremental downloader for 国家法律法规数据库 (https://flk.npc.gov.cn).

Public API — no login required.

Maps:
  宪法          → incoming/01_Constitution/
  法律          → incoming/02_Statutes/
  行政法规      → incoming/03_Administrative_Regulations/
  司法解释      → incoming/05_Judicial_Interpretations/

Only downloads PDF (official gazette version). Skips already-seen ids via
sources/flk-manifest.json. Newest-first, so weekly runs only touch the front
pages and exit early on known ids.

Usage (local first seed recommended):
  python scripts/download_flk.py --types 宪法,法律 --max-pages 20
  python scripts/download_flk.py --types 宪法,法律,行政法规,司法解释 --max-new 30

After PDFs land in incoming/, the existing convert-incoming workflow (or the
same job) turns them into Markdown under content/ and deletes the PDFs.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
INCOMING_ROOT = REPO_ROOT / "incoming"
MANIFEST_PATH = REPO_ROOT / "sources" / "flk-manifest.json"

LIST_URL = "https://flk.npc.gov.cn/api/"
DETAIL_URL = "https://flk.npc.gov.cn/api/detail"
DOWNLOAD_BASE = "https://wb.flk.npc.gov.cn"

# Chinese type → target folder (effect hierarchy)
TYPE_TO_FOLDER = {
    "宪法": "01_Constitution",
    "法律": "02_Statutes",
    "行政法规": "03_Administrative_Regulations",
    "司法解释": "05_Judicial_Interpretations",
    # "地方性法规": "04_Local_Regulations",  # intentionally omitted — too large
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Referer": "https://flk.npc.gov.cn/",
}


def safe_name(name: str) -> str:
    name = name or "untitled"
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-\.]+", "_", name, flags=re.UNICODE)
    return cleaned.strip("_ ")[:120] or "untitled"


def load_manifest() -> dict[str, Any]:
    if MANIFEST_PATH.exists():
        try:
            return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {"ids": {}, "last_run": None, "stats": {}}


def save_manifest(manifest: dict[str, Any]) -> None:
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    manifest["last_run"] = datetime.now(timezone.utc).isoformat()
    MANIFEST_PATH.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def fetch_list(page: int, size: int = 50) -> dict | None:
    params = {
        "page": str(page),
        "size": str(size),
        "type": "",  # empty = mixed, newest first under common sort
        "searchType": "title;vague",
        "sortTr": "f_bbrq_s;desc",
        "sort": "true",
        "_": str(int(time.time() * 1000)),
    }
    try:
        r = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True) and data.get("code") != 200:
            print(f"  list API error: {data}", file=sys.stderr)
            return None
        return data.get("result") or data
    except Exception as e:
        print(f"  list page={page} failed: {e}", file=sys.stderr)
        return None


def fetch_detail(law_id: str) -> dict | None:
    try:
        # Most crawlers use POST form data
        r = requests.post(
            DETAIL_URL,
            data={"id": law_id},
            headers=HEADERS,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()
        if not data.get("success", True) and data.get("code") != 200:
            print(f"  detail {law_id[:20]}... error: {data}", file=sys.stderr)
            return None
        return data.get("result") or data
    except Exception as e:
        print(f"  detail {law_id[:20]}... failed: {e}", file=sys.stderr)
        return None


def pick_pdf_path(detail: dict) -> str | None:
    body = detail.get("body") or []
    if not isinstance(body, list):
        return None
    # Prefer explicit PDF
    for item in body:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or ""
        typ = (item.get("type") or "").upper()
        if typ == "PDF" or path.lower().endswith(".pdf"):
            return path
    # Fallback: any path that looks like a file
    for item in body:
        if isinstance(item, dict):
            path = item.get("path") or ""
            if path and "." in path:
                return path
    return None


def download_pdf(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 1000:
        return True
    try:
        r = requests.get(url, headers=HEADERS, timeout=120, stream=True)
        r.raise_for_status()
        with open(dest, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
        if dest.stat().st_size < 500:
            dest.unlink(missing_ok=True)
            print(f"  too small, discarded: {dest.name}")
            return False
        return True
    except Exception as e:
        print(f"  download failed {url}: {e}", file=sys.stderr)
        dest.unlink(missing_ok=True)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Download from flk.npc.gov.cn into incoming/")
    parser.add_argument(
        "--types",
        default="宪法,法律",
        help="Comma-separated Chinese types to accept (default: 宪法,法律)",
    )
    parser.add_argument("--max-pages", type=int, default=30, help="Max list pages to scan")
    parser.add_argument("--max-new", type=int, default=50, help="Stop after this many new downloads")
    parser.add_argument("--size", type=int, default=50, help="Page size")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be downloaded")
    parser.add_argument("--sleep", type=float, default=1.2, help="Seconds between requests")
    args = parser.parse_args()

    wanted = {t.strip() for t in args.types.split(",") if t.strip()}
    for t in wanted:
        if t not in TYPE_TO_FOLDER:
            print(f"WARNING: type '{t}' has no folder mapping, will be skipped", file=sys.stderr)

    manifest = load_manifest()
    seen: dict = manifest.setdefault("ids", {})

    print(f"Wanted types: {sorted(wanted)}")
    print(f"Already in manifest: {len(seen)} ids")
    print(f"max-pages={args.max_pages}  max-new={args.max_new}  dry-run={args.dry_run}")

    new_count = 0
    scanned = 0
    page = 1

    while page <= args.max_pages and new_count < args.max_new:
        print(f"\n--- page {page} ---")
        result = fetch_list(page, size=args.size)
        if not result:
            break

        items = result.get("data") or []
        if not items:
            print("  empty page, stop")
            break

        for item in items:
            scanned += 1
            law_id = item.get("id") or ""
            title = (item.get("title") or "").strip()
            typ = (item.get("type") or "").strip()

            if not law_id or typ not in wanted:
                continue

            if law_id in seen:
                # Newest-first → once we hit a run of known ids we can stop early
                # but keep scanning a little for safety
                continue

            folder = TYPE_TO_FOLDER.get(typ)
            if not folder:
                continue

            print(f"  NEW [{typ}] {title[:60]}")

            if args.dry_run:
                new_count += 1
                continue

            time.sleep(args.sleep)
            detail = fetch_detail(law_id)
            if not detail:
                continue

            rel_path = pick_pdf_path(detail)
            if not rel_path:
                print(f"    no PDF path, skip")
                # still record so we don't retry forever
                seen[law_id] = {
                    "title": title,
                    "type": typ,
                    "status": "no-pdf",
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                continue

            full_url = DOWNLOAD_BASE + rel_path if rel_path.startswith("/") else rel_path
            fname = safe_name(title) + ".pdf"
            dest = INCOMING_ROOT / folder / fname

            time.sleep(args.sleep)
            if download_pdf(full_url, dest):
                print(f"    → {dest.relative_to(REPO_ROOT)}")
                seen[law_id] = {
                    "title": title,
                    "type": typ,
                    "file": str(dest.relative_to(REPO_ROOT)),
                    "at": datetime.now(timezone.utc).isoformat(),
                }
                new_count += 1
            else:
                seen[law_id] = {
                    "title": title,
                    "type": typ,
                    "status": "download-failed",
                    "at": datetime.now(timezone.utc).isoformat(),
                }

            if new_count >= args.max_new:
                break

        # Early exit heuristic: if entire page was already known, stop
        page_known = all((item.get("id") in seen) for item in items if item.get("type") in wanted)
        if page_known and page > 1:
            print("  page fully known → stop early")
            break

        page += 1
        time.sleep(args.sleep)

    if not args.dry_run:
        save_manifest(manifest)

    print(f"\nDone. scanned={scanned}  new={new_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

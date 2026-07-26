#!/usr/bin/env python3
"""
Incremental downloader for 国家法律法规数据库 (https://flk.npc.gov.cn).

Public API — no login required.

Current priority: fill 02_Statutes (法律) with small batches.
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

TYPE_TO_FOLDER = {
    "宪法": "01_Constitution",
    "法律": "02_Statutes",
    "行政法规": "03_Administrative_Regulations",
    "司法解释": "05_Judicial_Interpretations",
}

TYPE_CODE_CANDIDATES = {
    "法律": ["flfg", "", "fl"],
    "宪法": ["xf", ""],
    "行政法规": ["xzfg", ""],
    "司法解释": ["sfjs", ""],
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Referer": "https://flk.npc.gov.cn/",
    "Origin": "https://flk.npc.gov.cn",
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


def fetch_list(page: int, size: int = 30, type_code: str = "") -> dict | None:
    params = {
        "page": str(page),
        "size": str(size),
        "type": type_code,
        "searchType": "title;vague",
        "sortTr": "f_bbrq_s;desc",
        "sort": "true",
        "_": str(int(time.time() * 1000)),
    }
    try:
        r = requests.get(LIST_URL, params=params, headers=HEADERS, timeout=45)
        print(f"  GET {r.url}")
        print(f"  status={r.status_code}  content-type={r.headers.get('content-type')}")
        text = r.text
        print(f"  response length={len(text)}")
        if r.status_code != 200:
            print(f"  body[:800]: {text[:800]}", file=sys.stderr)
            return None
        try:
            data = r.json()
        except Exception as e:
            print(f"  JSON parse failed: {e}")
            print(f"  body[:800]: {text[:800]}")
            return None

        # Always dump first page for diagnosis
        if page == 1:
            print("  === RAW first-page keys ===")
            print(f"  top keys: {list(data.keys()) if isinstance(data, dict) else type(data)}")
            result = data.get("result") if isinstance(data, dict) else None
            if isinstance(result, dict):
                print(f"  result keys: {list(result.keys())}")
                items = result.get("data") or []
                print(f"  data length: {len(items)}")
                for i, it in enumerate(items[:3]):
                    print(f"  item[{i}]: type={it.get('type')!r} title={str(it.get('title',''))[:60]} id={str(it.get('id',''))[:30]}")
            else:
                print(f"  full response[:600]: {json.dumps(data, ensure_ascii=False)[:600]}")

        result = data.get("result") or data
        if isinstance(result, dict) and "data" in result:
            return result
        if isinstance(data, dict) and "data" in data:
            return data
        return None
    except Exception as e:
        print(f"  list page={page} EXCEPTION: {e}", file=sys.stderr)
        return None


def fetch_detail(law_id: str) -> dict | None:
    try:
        r = requests.post(DETAIL_URL, data={"id": law_id}, headers=HEADERS, timeout=45)
        print(f"  detail status={r.status_code}")
        if r.status_code != 200:
            print(f"  detail body: {r.text[:300]}", file=sys.stderr)
            return None
        data = r.json()
        return data.get("result") or data
    except Exception as e:
        print(f"  detail failed: {e}", file=sys.stderr)
        return None


def pick_pdf_path(detail: dict) -> str | None:
    body = detail.get("body") or []
    if not isinstance(body, list):
        return None
    for item in body:
        if not isinstance(item, dict):
            continue
        path = item.get("path") or ""
        typ = (item.get("type") or "").upper()
        if typ == "PDF" or path.lower().endswith(".pdf"):
            return path
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
        print(f"  download failed: {e}", file=sys.stderr)
        dest.unlink(missing_ok=True)
        return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--types", default="法律")
    parser.add_argument("--max-pages", type=int, default=10)
    parser.add_argument("--max-new", type=int, default=12)
    parser.add_argument("--size", type=int, default=20)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--sleep", type=float, default=1.5)
    args = parser.parse_args()

    wanted = {t.strip() for t in args.types.split(",") if t.strip()}
    manifest = load_manifest()
    seen: dict = manifest.setdefault("ids", {})

    print(f"Wanted types: {sorted(wanted)}")
    print(f"Already in manifest: {len(seen)} ids")
    print(f"max-pages={args.max_pages} max-new={args.max_new} dry-run={args.dry_run}")

    primary_type = next(iter(wanted))
    type_codes_to_try = TYPE_CODE_CANDIDATES.get(primary_type, [""])

    new_count = 0
    scanned = 0

    for type_code in type_codes_to_try:
        if new_count >= args.max_new:
            break
        print(f"\n=== trying type_code={type_code!r} ===")
        page = 1
        consecutive_empty = 0

        while page <= args.max_pages and new_count < args.max_new:
            print(f"\n--- page {page} ---")
            result = fetch_list(page, size=args.size, type_code=type_code)
            if not result:
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                page += 1
                time.sleep(args.sleep)
                continue

            items = result.get("data") or []
            if not items:
                print("  empty data list")
                consecutive_empty += 1
                if consecutive_empty >= 2:
                    break
                page += 1
                time.sleep(args.sleep)
                continue

            consecutive_empty = 0
            page_had_wanted = False

            for item in items:
                scanned += 1
                law_id = item.get("id") or ""
                title = (item.get("title") or "").strip()
                typ = (item.get("type") or "").strip()

                # Accept matching Chinese type, or any when using a type_code
                if typ and typ not in wanted:
                    continue
                if not typ and type_code == "":
                    continue

                page_had_wanted = True
                if not law_id or law_id in seen:
                    continue

                folder = TYPE_TO_FOLDER.get(typ) or TYPE_TO_FOLDER.get(primary_type)
                if not folder:
                    continue

                print(f"  NEW [{typ or primary_type}] {title[:60]}")

                if args.dry_run:
                    new_count += 1
                    continue

                time.sleep(args.sleep)
                detail = fetch_detail(law_id)
                if not detail:
                    continue

                rel_path = pick_pdf_path(detail)
                if not rel_path:
                    print("    no PDF path")
                    seen[law_id] = {"title": title, "type": typ or primary_type, "status": "no-pdf",
                                    "at": datetime.now(timezone.utc).isoformat()}
                    continue

                full_url = DOWNLOAD_BASE + rel_path if rel_path.startswith("/") else rel_path
                fname = safe_name(title) + ".pdf"
                dest = INCOMING_ROOT / folder / fname

                time.sleep(args.sleep)
                if download_pdf(full_url, dest):
                    print(f"    → {dest.relative_to(REPO_ROOT)}")
                    seen[law_id] = {"title": title, "type": typ or primary_type,
                                    "file": str(dest.relative_to(REPO_ROOT)),
                                    "at": datetime.now(timezone.utc).isoformat()}
                    new_count += 1
                else:
                    seen[law_id] = {"title": title, "type": typ or primary_type, "status": "download-failed",
                                    "at": datetime.now(timezone.utc).isoformat()}

                if new_count >= args.max_new:
                    break

            if not page_had_wanted and page > 2:
                print("  no wanted types → next type_code")
                break

            page += 1
            time.sleep(args.sleep)

        if new_count > 0:
            break

    if not args.dry_run:
        save_manifest(manifest)

    print(f"\nDone. scanned={scanned}  new={new_count}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

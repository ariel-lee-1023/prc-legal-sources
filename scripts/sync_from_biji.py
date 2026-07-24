#!/usr/bin/env python3
"""
Sync notes from biji.com knowledge base (topic_id=LYw7MjpY)
to this repository as Markdown files + attachments.

Requires environment variables:
  BIJI_API_KEY
  BIJI_CLIENT_ID

Usage:
  python scripts/sync_from_biji.py
"""

from __future__ import annotations

import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://openapi.biji.com/open/api/v1"
TOPIC_ID = "LYw7MjpY"
REPO_ROOT = Path(__file__).resolve().parent.parent
NOTES_DIR = REPO_ROOT / "sources" / "notes"
ATTACHMENTS_DIR = REPO_ROOT / "attachments"
MANIFEST_PATH = REPO_ROOT / "sources" / ".sync-manifest.json"


def get_api_key() -> str:
    key = os.environ.get("BIJI_API_KEY", "").strip()
    if not key:
        print("ERROR: BIJI_API_KEY is empty or not set", file=sys.stderr)
        sys.exit(1)
    return key


def get_client_id() -> str:
    cid = os.environ.get("BIJI_CLIENT_ID", "").strip()
    if not cid:
        print("ERROR: BIJI_CLIENT_ID is empty or not set", file=sys.stderr)
        sys.exit(1)
    return cid


def make_headers(use_bearer: bool = False) -> dict[str, str]:
    api_key = get_api_key()
    client_id = get_client_id()
    auth_value = f"Bearer {api_key}" if use_bearer else api_key
    return {
        "Authorization": auth_value,
        "X-Client-ID": client_id,
        "User-Agent": "prc-legal-sources-sync/1.0",
        "Accept": "application/json",
    }


def api_get(path: str, params: dict[str, Any] | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    last_error = None

    # Try both auth styles: plain key and Bearer prefix
    for use_bearer in (False, True):
        headers = make_headers(use_bearer=use_bearer)
        style = "Bearer" if use_bearer else "plain"
        try:
            resp = requests.get(url, headers=headers, params=params, timeout=60)
            if resp.status_code == 401:
                print(f"  [auth={style}] 401 Unauthorized. Response body: {resp.text[:500]}", file=sys.stderr)
                last_error = resp
                continue
            resp.raise_for_status()
            data = resp.json()
            if not data.get("success", True):
                raise RuntimeError(f"API error: {data}")
            print(f"  [auth={style}] OK")
            return data.get("data", data)
        except requests.exceptions.HTTPError as e:
            last_error = e.response if hasattr(e, "response") else None
            print(f"  [auth={style}] HTTP error: {e}", file=sys.stderr)
            if last_error is not None:
                print(f"  Response body: {last_error.text[:500]}", file=sys.stderr)

    # Both styles failed
    print("\nBoth auth styles failed. Please double-check:", file=sys.stderr)
    print("  1. BIJI_API_KEY is the full key (usually starts with gk_)", file=sys.stderr)
    print("  2. BIJI_CLIENT_ID is the full client id (usually starts with cli_)", file=sys.stderr)
    print("  3. The API Key is associated with '内置完整权限'", file=sys.stderr)
    print("  4. The knowledge base LYw7MjpY is owned by or subscribed under this account", file=sys.stderr)
    if last_error is not None:
        raise requests.exceptions.HTTPError(
            f"401 Unauthorized after trying both auth styles. Last body: {last_error.text[:300]}",
            response=last_error,
        )
    raise RuntimeError("All auth attempts failed")


def slugify(title: str, note_id: str) -> str:
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", title.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if not cleaned:
        cleaned = "untitled"
    short_id = note_id[-8:] if len(note_id) > 8 else note_id
    return f"{cleaned[:80]}-{short_id}"


def fetch_all_notes() -> list[dict]:
    notes: list[dict] = []
    page = 1
    while True:
        data = api_get("/resource/knowledge/notes", {"topic_id": TOPIC_ID, "page": page})
        batch = data.get("notes") or data.get("list") or []
        if not batch:
            break
        notes.extend(batch)
        if not data.get("has_more", False):
            break
        page += 1
        if page > 100:
            break
    return notes


def fetch_note_detail(note_id: str) -> dict:
    data = api_get("/resource/note/detail", {"id": note_id, "image_quality": "original"})
    return data.get("note") or data


def download_attachment(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    # Prefer plain key for downloads (same as successful list)
    r = requests.get(url, headers=make_headers(use_bearer=False), timeout=120, stream=True)
    r.raise_for_status()
    with open(dest, "wb") as f:
        for chunk in r.iter_content(chunk_size=8192):
            f.write(chunk)


def write_note(note: dict, detail: dict) -> str:
    note_id = str(note.get("note_id") or note.get("id"))
    title = note.get("title") or detail.get("title") or "untitled"
    content = detail.get("content") or note.get("content") or ""
    updated = note.get("updated_at") or detail.get("updated_at") or ""

    slug = slugify(title, note_id)
    md_path = NOTES_DIR / f"{slug}.md"
    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    front = [
        "---",
        f"note_id: {note_id}",
        f"title: {json.dumps(title, ensure_ascii=False)}",
        f"updated_at: {updated}",
        f"source: biji",
        f"topic_id: {TOPIC_ID}",
        "---",
        "",
        f"# {title}",
        "",
        content.strip(),
        "",
    ]

    attachments = detail.get("attachments") or []
    if attachments:
        front.append("## Attachments\n")
        for i, att in enumerate(attachments):
            att_type = att.get("type", "file")
            url = att.get("url") or att.get("play_url") or ""
            if not url:
                continue
            ext = Path(url).suffix or (".png" if att_type == "image" else ".bin")
            fname = f"{slug}-{i}{ext}"
            dest = ATTACHMENTS_DIR / fname
            try:
                download_attachment(url, dest)
                front.append(f"- [{att_type}](../attachments/{fname})")
            except Exception as e:
                front.append(f"- [{att_type}]({url})  <!-- download failed: {e} -->")

    md_path.write_text("\n".join(front), encoding="utf-8")
    return str(md_path.relative_to(REPO_ROOT))


def main() -> None:
    print(f"[{datetime.now(timezone.utc).isoformat()}] Starting sync for topic {TOPIC_ID}")
    print(f"API Key length: {len(get_api_key())}, Client ID length: {len(get_client_id())}")

    # First probe: list knowledge bases to verify credentials work at all
    print("Probing credentials with /resource/knowledge/list ...")
    try:
        kb_data = api_get("/resource/knowledge/list", {"page": 1})
        topics = kb_data.get("topics") or kb_data.get("list") or []
        print(f"  Credentials OK. Found {len(topics)} knowledge base(s).")
        for t in topics[:5]:
            tid = t.get("topic_id") or t.get("id")
            name = t.get("name") or ""
            print(f"    - {tid}: {name}")
    except Exception as e:
        print(f"  Knowledge list probe failed: {e}", file=sys.stderr)
        print("  Will still try the notes endpoint...", file=sys.stderr)

    notes = fetch_all_notes()
    print(f"Found {len(notes)} notes")

    written: list[str] = []
    for note in notes:
        note_id = str(note.get("note_id") or note.get("id"))
        try:
            detail = fetch_note_detail(note_id)
            path = write_note(note, detail)
            written.append(path)
            print(f"  ✓ {path}")
        except Exception as e:
            print(f"  ✗ note {note_id}: {e}", file=sys.stderr)

    manifest = {
        "topic_id": TOPIC_ID,
        "synced_at": datetime.now(timezone.utc).isoformat(),
        "note_count": len(notes),
        "files": written,
    }
    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST_PATH.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Sync complete. {len(written)} files written.")


if __name__ == "__main__":
    main()

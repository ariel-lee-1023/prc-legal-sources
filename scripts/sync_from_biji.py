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

import hashlib
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


def get_headers() -> dict[str, str]:
    api_key = os.environ.get("BIJI_API_KEY")
    client_id = os.environ.get("BIJI_CLIENT_ID")
    if not api_key or not client_id:
        print("ERROR: BIJI_API_KEY and BIJI_CLIENT_ID must be set", file=sys.stderr)
        sys.exit(1)
    return {
        "Authorization": api_key,
        "X-Client-ID": client_id,
        "User-Agent": "prc-legal-sources-sync/1.0",
    }


def api_get(path: str, params: dict[str, Any] | None = None) -> dict:
    url = f"{BASE_URL}{path}"
    resp = requests.get(url, headers=get_headers(), params=params, timeout=60)
    resp.raise_for_status()
    data = resp.json()
    if not data.get("success", True):
        raise RuntimeError(f"API error: {data}")
    return data.get("data", data)


def slugify(title: str, note_id: str) -> str:
    # Keep Chinese + alphanumeric, collapse spaces
    cleaned = re.sub(r"[^\w\u4e00-\u9fff\-]+", "-", title.strip())
    cleaned = re.sub(r"-+", "-", cleaned).strip("-")
    if not cleaned:
        cleaned = "untitled"
    # Limit length and always append short id for uniqueness
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
        if page > 100:  # safety
            break
    return notes


def fetch_note_detail(note_id: str) -> dict:
    data = api_get("/resource/note/detail", {"id": note_id, "image_quality": "original"})
    return data.get("note") or data


def download_attachment(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return
    r = requests.get(url, headers=get_headers(), timeout=120, stream=True)
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

    # Front matter
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

    # Attachments
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

    # Manifest for change detection
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

#!/usr/bin/env python3
"""
Diagnostic: probe biji topic 0QWLLvBn for notes + PDF attachments.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

BASE_URL = "https://openapi.biji.com/open/api/v1"
TARGET_TOPIC = "0QWLLvBn"


def get_api_key() -> str:
    key = os.environ.get("BIJI_API_KEY", "").strip()
    if not key:
        print("ERROR: BIJI_API_KEY empty", file=sys.stderr)
        sys.exit(1)
    return key


def get_client_id() -> str:
    cid = os.environ.get("BIJI_CLIENT_ID", "").strip()
    if not cid:
        print("ERROR: BIJI_CLIENT_ID empty", file=sys.stderr)
        sys.exit(1)
    return cid


def headers() -> dict[str, str]:
    return {
        "Authorization": get_api_key(),
        "X-Client-ID": get_client_id(),
        "User-Agent": "prc-legal-sources-probe/1.1",
        "Accept": "application/json",
    }


def api_get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    try:
        resp = requests.get(f"{BASE_URL}{path}", headers=headers(), params=params, timeout=45)
        if resp.status_code == 200:
            return 200, resp.json()
        return resp.status_code, resp.text[:1000]
    except Exception as e:
        return 0, str(e)


def main() -> None:
    print(f"Target topic_id: {TARGET_TOPIC}")
    print(f"API Key len={len(get_api_key())}, Client ID len={len(get_client_id())}")

    # 1. Is it in created list?
    print("\n=== 1. 我创建的知识库 ===")
    status, data = api_get("/resource/knowledge/list", {"page": 1})
    if status == 200:
        payload = data.get("data", data)
        topics = payload.get("topics") or payload.get("list") or []
        found = False
        for t in topics:
            tid = t.get("topic_id") or t.get("id")
            if tid == TARGET_TOPIC:
                found = True
                print(f"  FOUND in created: {t.get('name')}  notes≈{(t.get('stats') or {}).get('note_count')}")
        if not found:
            print(f"  Not in first page of created list (total shown: {len(topics)})")
            for t in topics[:5]:
                print(f"    - {t.get('topic_id')}: {t.get('name')}")
    else:
        print(f"  FAILED {status}: {data}")

    # 2. Is it in subscribed list?
    print("\n=== 2. 我订阅的知识库 ===")
    status, data = api_get("/resource/knowledge/subscribe/list", {"page": 1})
    if status == 200:
        payload = data.get("data", data)
        topics = payload.get("topics") or payload.get("list") or payload.get("items") or []
        found = False
        for t in topics:
            tid = t.get("topic_id") or t.get("id")
            name = t.get("name") or ""
            if tid == TARGET_TOPIC:
                found = True
                print(f"  FOUND in subscribed: {name}")
            else:
                print(f"    - {tid}: {name}")
        if not found:
            print(f"  Target NOT found in subscribed list")
    else:
        print(f"  FAILED {status}: {data}")

    # 3. List notes
    print(f"\n=== 3. 笔记列表 topic_id={TARGET_TOPIC} ===")
    status, data = api_get("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1})
    notes = []
    if status == 200:
        payload = data.get("data", data)
        notes = payload.get("notes") or payload.get("list") or []
        print(f"  Found {len(notes)} notes on page 1")
        has_more = payload.get("has_more")
        print(f"  has_more={has_more}")
        for n in notes[:8]:
            nid = n.get("note_id") or n.get("id")
            title = (n.get("title") or "")[:50]
            ntype = n.get("note_type") or ""
            print(f"    - {nid}: [{ntype}] {title}")
    else:
        print(f"  FAILED {status}: {data}")
        return

    # 4. Inspect first few notes for PDF attachments
    print("\n=== 4. 检查前几个笔记的附件（找 PDF） ===")
    pdf_count = 0
    for n in notes[:5]:
        nid = str(n.get("note_id") or n.get("id"))
        title = n.get("title") or ""
        print(f"\n  Note {nid}: {title[:40]}")
        status, detail = api_get("/resource/note/detail", {"id": nid, "image_quality": "original"})
        if status != 200:
            print(f"    detail failed: {status} {str(detail)[:200]}")
            continue
        note = (detail.get("data") or detail).get("note") or detail.get("data") or detail
        atts = note.get("attachments") or []
        print(f"    attachments: {len(atts)}")
        for a in atts:
            atype = a.get("type") or ""
            url = a.get("url") or a.get("play_url") or a.get("file_url") or ""
            name = a.get("name") or a.get("filename") or ""
            print(f"      - type={atype} name={name} url={url[:80]}...")
            if "pdf" in (atype + name + url).lower():
                pdf_count += 1
                print("        *** PDF detected ***")
        # also check content for pdf links
        content = note.get("content") or ""
        if ".pdf" in content.lower():
            print("    content mentions .pdf")

    print(f"\n=== Summary: found {pdf_count} PDF attachments in sampled notes ===")


if __name__ == "__main__":
    main()

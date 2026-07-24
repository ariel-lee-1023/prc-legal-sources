#!/usr/bin/env python3
"""
Probe topic 0QWLLvBn for FILES (PDFs), not just notes.
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

BASE_URL = "https://openapi.biji.com/open/api/v1"
TARGET_TOPIC = "0QWLLvBn"


def headers() -> dict[str, str]:
    return {
        "Authorization": os.environ["BIJI_API_KEY"].strip(),
        "X-Client-ID": os.environ["BIJI_CLIENT_ID"].strip(),
        "User-Agent": "prc-legal-sources-probe/1.2",
        "Accept": "application/json",
    }


def try_get(path: str, params: dict[str, Any] | None = None) -> None:
    url = f"{BASE_URL}{path}"
    try:
        r = requests.get(url, headers=headers(), params=params or {}, timeout=30)
        print(f"\nGET {path}  params={params}")
        print(f"  status={r.status_code}")
        text = r.text[:1200]
        try:
            data = r.json()
            print(f"  success={data.get('success')}")
            payload = data.get("data") or data
            if isinstance(payload, dict):
                keys = list(payload.keys())
                print(f"  data keys: {keys}")
                for k in ("list", "notes", "files", "resources", "items", "topics"):
                    if k in payload and isinstance(payload[k], list):
                        print(f"  {k} count: {len(payload[k])}")
                        for item in payload[k][:4]:
                            if isinstance(item, dict):
                                nid = item.get("id") or item.get("note_id") or item.get("file_id") or item.get("resource_id")
                                title = item.get("title") or item.get("name") or item.get("filename") or ""
                                ntype = item.get("type") or item.get("note_type") or item.get("file_type") or ""
                                print(f"    - {nid} [{ntype}] {str(title)[:60]}")
            else:
                print(f"  data type: {type(payload)}")
            if r.status_code != 200:
                print(f"  body: {text}")
        except Exception:
            print(f"  raw: {text}")
    except Exception as e:
        print(f"  EXCEPTION: {e}")


def main() -> None:
    print(f"Target: {TARGET_TOPIC}")
    print(f"Key len={len(os.environ.get('BIJI_API_KEY',''))}  Client len={len(os.environ.get('BIJI_CLIENT_ID',''))}")

    # Known notes endpoint (baseline)
    try_get("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1})

    # Candidate file / resource endpoints
    candidates = [
        ("/resource/knowledge/files", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/file/list", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/file/list", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/resources", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/resource/list", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/content", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/contents", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/all", {"topic_id": TARGET_TOPIC, "page": 1}),
        ("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1, "type": "file"}),
        ("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1, "note_type": "file"}),
        ("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1, "content_type": "pdf"}),
        ("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1, "filter": "file"}),
        ("/open/api/v1/resource/knowledge/files", {"topic_id": TARGET_TOPIC}),  # wrong base, skip
    ]

    for path, params in candidates:
        if path.startswith("/open"):
            continue
        try_get(path, params)

    # Also try note list without topic filter / with different resource type
    print("\n=== Extra: knowledge detail ===")
    try_get("/resource/knowledge/detail", {"topic_id": TARGET_TOPIC})
    try_get("/resource/knowledge/info", {"topic_id": TARGET_TOPIC})

    print("\nDone.")


if __name__ == "__main__":
    main()

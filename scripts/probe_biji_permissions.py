#!/usr/bin/env python3
"""
Diagnostic script: probe biji OpenAPI permissions for created vs subscribed knowledge bases.

Only prints results, does NOT write any files.

Requires:
  BIJI_API_KEY
  BIJI_CLIENT_ID
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any

import requests

BASE_URL = "https://openapi.biji.com/open/api/v1"
TARGET_TOPIC = "LYw7MjpY"


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
        "User-Agent": "prc-legal-sources-probe/1.0",
        "Accept": "application/json",
    }


def try_get(path: str, params: dict[str, Any] | None = None) -> tuple[int, Any]:
    """Try plain then Bearer. Returns (status_code, data_or_error_text)."""
    last_status = 0
    last_body = ""
    for use_bearer in (False, True):
        style = "Bearer" if use_bearer else "plain"
        headers = make_headers(use_bearer=use_bearer)
        try:
            resp = requests.get(f"{BASE_URL}{path}", headers=headers, params=params, timeout=30)
            last_status = resp.status_code
            last_body = resp.text[:800]
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    print(f"  [auth={style}] 200 OK")
                    return 200, data
                except Exception:
                    return 200, {"raw": last_body}
            else:
                print(f"  [auth={style}] {resp.status_code}")
        except Exception as e:
            print(f"  [auth={style}] exception: {e}")
            last_body = str(e)
    return last_status, last_body


def print_section(title: str) -> None:
    print("\n" + "=" * 60)
    print(title)
    print("=" * 60)


def main() -> None:
    print(f"API Key length: {len(get_api_key())}")
    print(f"Client ID length: {len(get_client_id())}")
    print(f"Target topic_id: {TARGET_TOPIC}")

    # 1. My created knowledge bases
    print_section("1. 我创建的知识库  GET /resource/knowledge/list")
    status, data = try_get("/resource/knowledge/list", {"page": 1})
    if status == 200:
        payload = data.get("data", data) if isinstance(data, dict) else data
        topics = []
        if isinstance(payload, dict):
            topics = payload.get("topics") or payload.get("list") or []
        print(f"  Found {len(topics)} created knowledge base(s):")
        for t in topics[:10]:
            if isinstance(t, dict):
                tid = t.get("topic_id") or t.get("id") or "?"
                name = t.get("name") or ""
                count = (t.get("stats") or {}).get("note_count", "?")
                print(f"    - {tid}: {name}  (notes≈{count})")
        if not topics:
            print("  (empty list)")
            print(f"  Raw response keys: {list(payload.keys()) if isinstance(payload, dict) else type(payload)}")
    else:
        print(f"  FAILED status={status}")
        print(f"  Body: {data}")

    # 2. My subscribed knowledge bases
    print_section("2. 我订阅的知识库  GET /resource/knowledge/subscribe/list")
    status, data = try_get("/resource/knowledge/subscribe/list", {"page": 1})
    if status == 200:
        payload = data.get("data", data) if isinstance(data, dict) else data
        topics = []
        if isinstance(payload, dict):
            topics = payload.get("topics") or payload.get("list") or payload.get("items") or []
        print(f"  Found {len(topics)} subscribed knowledge base(s):")
        found_target = False
        for t in topics[:15]:
            if isinstance(t, dict):
                tid = t.get("topic_id") or t.get("id") or "?"
                name = t.get("name") or ""
                print(f"    - {tid}: {name}")
                if tid == TARGET_TOPIC:
                    found_target = True
                    print("      ^^^ THIS IS OUR TARGET")
        if not topics:
            print("  (empty list)")
            print(f"  Raw response: {json.dumps(payload, ensure_ascii=False)[:600]}")
        if not found_target and topics:
            print(f"\n  Target {TARGET_TOPIC} NOT found in the subscribed list returned by API.")
    else:
        print(f"  FAILED status={status}")
        print(f"  Body: {data}")

    # 3. Try to list notes of the target topic
    print_section(f"3. 目标知识库笔记列表  GET /resource/knowledge/notes?topic_id={TARGET_TOPIC}")
    status, data = try_get("/resource/knowledge/notes", {"topic_id": TARGET_TOPIC, "page": 1})
    if status == 200:
        payload = data.get("data", data) if isinstance(data, dict) else data
        notes = []
        if isinstance(payload, dict):
            notes = payload.get("notes") or payload.get("list") or []
        print(f"  SUCCESS! Found {len(notes)} notes on first page.")
        for n in notes[:3]:
            if isinstance(n, dict):
                print(f"    - {n.get('note_id')}: {n.get('title', '')[:40]}")
    else:
        print(f"  FAILED status={status}")
        print(f"  Body: {data}")

    print_section("Summary")
    print("If step 1 works but step 2/3 fail → API only allows created knowledge bases.")
    print("If step 2 returns the target but step 3 fails → notes endpoint is restricted for subscribed KBs.")
    print("If everything returns 401 → credentials or scope problem.")


if __name__ == "__main__":
    main()

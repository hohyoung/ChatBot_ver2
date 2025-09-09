#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
/api/debug/search 엔드포인트를 호출해
- 랭크, 거리, 제목, 스니펫을 출력합니다.
"""
import os, sys, json
from typing import Any, Dict
try:
    import requests
except ImportError:
    print("requests 가 필요합니다. (backend 가상환경에서)\n  python -m pip install requests")
    sys.exit(1)

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
URL = f"{API_BASE}/api/debug/search"

def main():
    question = "장기현장실습생 신청 절차"
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])
    payload = {"question": question, "k": 5}
    r = requests.post(URL, json=payload, timeout=60)
    if r.status_code != 200:
        print(f"[ERR] HTTP {r.status_code}")
        print(r.text); sys.exit(2)
    res: Dict[str, Any] = r.json()
    print(f"\n[SEARCH] {question}")
    for item in res.get("results", []):
        print(f"- #{item['rank']:>2} dist={item['distance']:.4f}  title={item.get('doc_title')}  id={item.get('chunk_id')}")
        print(f"      {item.get('snippet')}")
    if not res.get("results"):
        print("(결과 없음)")

if __name__ == "__main__":
    main()

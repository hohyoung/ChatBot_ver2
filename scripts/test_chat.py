#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
/api/chat.debug 엔드포인트를 호출해
- 답변 텍스트
- 사용된 청크(doc_title, chunk_id, snippet)
를 보기 좋게 출력합니다.
"""
import os, sys, json, textwrap
from typing import Any, Dict, List

try:
    import requests
except ImportError:
    print(
        "requests 가 필요합니다.  (backend 가상환경에서)\n  python -m pip install requests"
    )
    sys.exit(1)

API_BASE = os.environ.get("API_BASE", "http://127.0.0.1:8000")
URL = f"{API_BASE}/api/chat.debug"


def main():
    question = "장기현장실습생 안내자료의 주요 신청 절차를 요약해줘"
    if len(sys.argv) > 1:
        question = " ".join(sys.argv[1:])

    payload = {"question": question}
    try:
        r = requests.post(URL, json=payload, timeout=60)
    except Exception as e:
        print(f"[ERR] 요청 실패: {e}")
        sys.exit(1)

    if r.status_code != 200:
        print(f"[ERR] HTTP {r.status_code}")
        print(r.text)
        sys.exit(2)

    data = r.json()
    print(f"\n[Q] {question}\n")
    ans = data.get("data", {}).get("answer") or data.get("answer")
    print("[A]")
    print(textwrap.fill(ans or "(빈 응답)", width=100))
    print("\n[USED CHUNKS]")
    chunks: List[Dict[str, Any]] = (
        data.get("data", {}).get("chunks") or data.get("chunks") or []
    )
    if not chunks:
        print("(없음)")
    else:
        for i, ch in enumerate(chunks, start=1):
            title = ch.get("doc_title") or ch.get("doc_id")
            cid = ch.get("chunk_id")
            snip = (ch.get("content") or "")[:160].replace("\n", " ")
            print(f"- [{i}] {title} :: {cid} :: {snip}...")


if __name__ == "__main__":
    main()

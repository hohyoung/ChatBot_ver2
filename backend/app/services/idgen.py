from __future__ import annotations
import time, secrets, base64


def new_id(prefix: str = "id") -> str:
    """
    접두사+고해상도 타임스탬프+난수로 충돌 가능성이 매우 낮은 ID 생성.
    예: ans_18e3a1f4b3a8c000_2pNf8Q
    """
    nanos = int(time.time() * 1e9)
    rnd = base64.urlsafe_b64encode(secrets.token_bytes(4)).decode().rstrip("=")
    return f"{prefix}_{nanos:x}_{rnd}"

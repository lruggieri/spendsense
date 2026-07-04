"""In-memory per-key sliding-window rate limiter (defense against runaway loops).

Per-process only; with multiple workers the effective ceiling is limit x workers.
Not a security boundary."""
from collections import deque
from typing import Deque, Dict


class RateLimiter:
    def __init__(self, limit_per_min: int):
        self.limit = limit_per_min
        self._hits: Dict[str, Deque[float]] = {}

    def check(self, key_id: str, now: float) -> bool:
        dq = self._hits.setdefault(key_id, deque())
        cutoff = now - 60.0
        while dq and dq[0] <= cutoff:
            dq.popleft()
        if len(dq) >= self.limit:
            return False
        dq.append(now)
        return True

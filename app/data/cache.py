import threading
import time
from typing import Generic, TypeVar

# 단일 프로세스용 in-memory TTL 캐시 (feature-spec §2). 본격 캐시/배치는 B4.
# fdr 호출은 threadpool에서 실행되므로 락으로 보호한다.

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(Generic[K, V]):
    def __init__(self, ttl_seconds: float) -> None:
        self._ttl = ttl_seconds
        self._store: dict[K, tuple[float, V]] = {}
        self._lock = threading.Lock()

    def get(self, key: K) -> V | None:
        now = time.monotonic()

        with self._lock:
            entry = self._store.get(key)

            if entry is None:
                return None

            expires_at, value = entry

            if now >= expires_at:
                del self._store[key]
                return None

            return value

    def set(self, key: K, value: V) -> None:
        with self._lock:
            self._store[key] = (time.monotonic() + self._ttl, value)

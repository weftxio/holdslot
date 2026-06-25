"""Tiny in-process TTL cache (W8).

A warm Lambda container reuses module globals across invocations, so a short-TTL dict memoizes
repeated identical work without any external store (no Redis to run/pay at this stage). Two uses:

  * the people-facet sidebar — ~26 free-but-slow Apollo `count_people` probes per open, memoized as
    one result so a re-open / re-tick of the same company set is instant;
  * company search — the credit-costing Apollo call, so a rapid re-run of the same scope (a
    double-click, or re-finding within the window) serves the prior rows instead of spending again.

Keys must be hashable AND already scope-correct (include tenant where results are tenant-specific;
company-search rows are pure Apollo data, identical for any caller, so that key is global). Values
are treated as immutable. Bounded so a long-lived container can't grow without limit. Single-process
+ short TTL means at worst a request recomputes — never a correctness risk.
"""

from __future__ import annotations

import time
from typing import Any


class TTLCache:
    def __init__(self, ttl_seconds: float, max_entries: int = 256) -> None:
        self.ttl = ttl_seconds
        self.max = max_entries
        self._store: dict[Any, tuple[float, Any]] = {}

    def get(self, key: Any) -> Any | None:
        """Return the cached value, or None if absent/expired (expired entries are dropped)."""
        hit = self._store.get(key)
        if hit is None:
            return None
        expires_at, value = hit
        if expires_at < time.monotonic():
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: Any, value: Any) -> None:
        """Cache `value` under `key` for the TTL, purging expired (then oldest) when full."""
        if key not in self._store and len(self._store) >= self.max:
            now = time.monotonic()
            for k in [k for k, (exp, _) in self._store.items() if exp < now]:
                self._store.pop(k, None)
            if len(self._store) >= self.max:
                self._store.pop(next(iter(self._store)), None)  # drop the oldest-inserted entry
        self._store[key] = (time.monotonic() + self.ttl, value)

    def clear(self) -> None:
        self._store.clear()

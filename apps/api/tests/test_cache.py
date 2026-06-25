"""TTLCache (W8) — pure get/set/expiry/eviction. No DB; uses a monotonic clock internally."""

import time

from app.core.cache import TTLCache


def test_get_returns_set_value():
    c = TTLCache(ttl_seconds=10)
    c.set("k", 123)
    assert c.get("k") == 123


def test_miss_returns_none():
    assert TTLCache(ttl_seconds=10).get("absent") is None


def test_expiry_drops_value():
    c = TTLCache(ttl_seconds=0.05)
    c.set("k", "v")
    time.sleep(0.07)
    assert c.get("k") is None


def test_eviction_bounds_size():
    c = TTLCache(ttl_seconds=100, max_entries=3)
    for i in range(10):
        c.set(f"k{i}", i)
    # Never grows past the cap; recent keys survive.
    assert len(c._store) <= 3
    assert c.get("k9") == 9


def test_clear_empties():
    c = TTLCache(ttl_seconds=100)
    c.set("k", 1)
    c.clear()
    assert c.get("k") is None

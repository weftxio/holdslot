"""Opaque cursor codec for the list feeds (W5).

Offset cursors, not keyset: the web app auto-loads every page on mount up to a 250-row ceiling,
so the whole feed is fetched within a few seconds — the brief window in which an offset could
drift (a row inserted between page fetches) is immaterial here, and the much simpler offset form
is exactly verifiable. The cursor is base64url(`o:<offset>`) so it stays OPAQUE to the client:
the API can switch to keyset later without changing the contract (clients only ever echo it back).
"""

from __future__ import annotations

import base64

from fastapi import HTTPException, status

DEFAULT_PAGE = 100
MAX_PAGE = 250  # the auto-load ceiling — one request can return at most this many rows


def encode_cursor(offset: int) -> str:
    """Encode the next-page offset into the opaque cursor string."""
    return base64.urlsafe_b64encode(f"o:{offset}".encode()).decode()


def decode_cursor(cursor: str | None) -> int:
    """Decode a cursor back to its offset; `None`/empty → 0 (first page).

    A malformed cursor is a client error, not a server one — raise 400 rather than 500 so a
    stale/hand-edited cursor surfaces cleanly instead of leaking a decode traceback.
    """
    if not cursor:
        return 0
    try:
        raw = base64.urlsafe_b64decode(cursor.encode()).decode()
        prefix, _, value = raw.partition(":")
        if prefix != "o":
            raise ValueError("bad cursor prefix")
        offset = int(value)
        if offset < 0:
            raise ValueError("negative offset")
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid cursor") from exc
    return offset

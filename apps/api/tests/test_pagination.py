"""Cursor codec (W5) — pure round-trip + malformed-input handling. No DB."""

import pytest
from fastapi import HTTPException

from app.core.pagination import decode_cursor, encode_cursor


@pytest.mark.parametrize("offset", [0, 1, 100, 250, 999_999])
def test_roundtrip(offset):
    assert decode_cursor(encode_cursor(offset)) == offset


def test_none_and_empty_are_first_page():
    assert decode_cursor(None) == 0
    assert decode_cursor("") == 0


def test_cursor_is_opaque():
    # The offset must not be readable straight off the wire (it's base64url, not the bare int).
    assert encode_cursor(42) != "42"


@pytest.mark.parametrize(
    "bad",
    [
        "not-base64!!!",  # invalid base64
        "Zm9vOmJhcg==",  # decodes to "foo:bar" — wrong prefix
        encode_cursor(0)[:-2] + "==",  # truncated/garbled payload
    ],
)
def test_malformed_cursor_is_400(bad):
    with pytest.raises(HTTPException) as exc:
        decode_cursor(bad)
    assert exc.value.status_code == 400


def test_negative_offset_rejected():
    import base64

    forged = base64.urlsafe_b64encode(b"o:-5").decode()
    with pytest.raises(HTTPException) as exc:
        decode_cursor(forged)
    assert exc.value.status_code == 400

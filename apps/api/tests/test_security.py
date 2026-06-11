"""Unit tests for security primitives — no AWS, no DB."""

import jwt
import pytest

from app.core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    hash_token,
    new_opaque_token,
    verify_password,
)

KEY = "test-signing-key-at-least-32-chars-long!!"
RKEY = "test-refresh-key-at-least-32-chars-long!!"


def test_password_hash_roundtrip():
    h = hash_password("tryholdslot1!")
    assert h.startswith("$argon2id$")
    assert verify_password(h, "tryholdslot1!")
    assert not verify_password(h, "wrong")


def test_token_hash_is_deterministic_sha256():
    t = new_opaque_token()
    assert hash_token(t) == hash_token(t)
    assert len(hash_token(t)) == 64
    assert hash_token(t) != hash_token(new_opaque_token())


def test_access_token_roundtrip():
    tok = create_access_token("user-123", KEY, 60)
    payload = decode_token(tok, KEY, "access")
    assert payload["sub"] == "user-123"
    assert payload["type"] == "access"


def test_refresh_token_roundtrip_and_jti():
    tok, jti = create_refresh_token("user-123", RKEY, 60)
    payload = decode_token(tok, RKEY, "refresh")
    assert payload["sub"] == "user-123"
    assert payload["jti"] == jti


def test_wrong_type_rejected():
    access = create_access_token("u", KEY, 60)
    with pytest.raises(jwt.InvalidTokenError):
        decode_token(access, KEY, "refresh")


def test_wrong_key_rejected():
    access = create_access_token("u", KEY, 60)
    with pytest.raises(jwt.InvalidSignatureError):
        decode_token(access, "different-key-also-32-chars-long-xx", "access")


def test_expired_token_rejected():
    tok = create_access_token("u", KEY, -1)  # already expired
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_token(tok, KEY, "access")

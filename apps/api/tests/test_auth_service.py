"""Auth service — refresh-token rotation guards (N9/N33/N36). Fake session, real JWTs; no AWS/DB."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from sqlalchemy import Delete, Select, Update

from app.core.security import create_refresh_token, hash_token
from app.domains.auth import service
from app.models import UserStatus

RKEY = "test-refresh-key-at-least-32-chars-long!!"
SKEY = "test-signing-key-at-least-32-chars-long!!"


class _Row:
    def __init__(self, token_hash: str, expires_at: datetime):
        self.id = "refresh-row-1"
        self.token_hash = token_hash
        self.expires_at = expires_at
        self.revoked_at: datetime | None = None


class _ScalarResult:
    def __init__(self, row):
        self._row = row

    def scalar_one_or_none(self):
        return self._row


class _RowCount:
    def __init__(self, rowcount: int):
        self.rowcount = rowcount


class _Db:
    """Minimal session branching on statement type: SELECT → the seeded row; the N33 guarded UPDATE
    consumes the token once (rowcount 1, then 0); the N36 DELETE is a no-op. Records commits."""

    def __init__(self, row, user):
        self._row = row
        self._user = user
        self.committed = False

    def execute(self, stmt):
        if isinstance(stmt, Select):
            return _ScalarResult(self._row)
        if isinstance(stmt, Update):
            # Guarded single-use revoke: succeeds only while the row is still un-revoked.
            if self._row is not None and self._row.revoked_at is None:
                self._row.revoked_at = datetime.now(UTC)
                return _RowCount(1)
            return _RowCount(0)
        if isinstance(stmt, Delete):
            return _RowCount(0)  # N36 opportunistic prune — no expired rows seeded
        return _RowCount(0)

    def get(self, _model, _id):
        return self._user

    def add(self, _obj):
        pass

    def commit(self):
        self.committed = True


def _settings():
    return SimpleNamespace(
        jwt_refresh_key=RKEY,
        jwt_signing_key=SKEY,
        access_ttl_seconds=60,
        refresh_ttl_seconds=3600,
    )


def _fresh_row(raw: str) -> _Row:
    return _Row(hash_token(raw), datetime.now(UTC) + timedelta(hours=1))


def test_rotate_refresh_rejects_disabled_user_without_revoking(monkeypatch):
    # N9 — a disabled user must not keep minting access tokens by rotating a still-valid refresh
    # token. Reject, and leave the presented token intact so a re-enabled user can resume with it.
    monkeypatch.setattr(service, "get_settings", _settings)
    raw, _jti = create_refresh_token("user-1", RKEY, 3600)
    row = _fresh_row(raw)
    db = _Db(row, SimpleNamespace(id="user-1", status=UserStatus.disabled))

    assert service.rotate_refresh(db, raw) is None
    assert row.revoked_at is None  # not consumed
    assert db.committed is False  # no new pair issued


def test_rotate_refresh_active_user_rotates_and_consumes_token(monkeypatch):
    monkeypatch.setattr(service, "get_settings", _settings)
    raw, _jti = create_refresh_token("user-1", RKEY, 3600)
    row = _fresh_row(raw)
    user = SimpleNamespace(id="user-1", status=UserStatus.active)
    db = _Db(row, user)

    out = service.rotate_refresh(db, raw)
    assert out is not None
    user_out, pair = out
    assert user_out is user
    assert pair.access_token and pair.refresh_token
    assert row.revoked_at is not None  # the guarded UPDATE consumed the token
    assert db.committed is True

    # N33 — single-use is atomic: a second rotation of the SAME token (row now revoked) wins no rows
    # in the guarded UPDATE (rowcount 0) and is rejected, so one refresh token can't mint two pairs.
    assert service.rotate_refresh(db, raw) is None


def test_rotate_refresh_lost_write_race_rejected(monkeypatch):
    # N33 — the concurrent-race path proper: the read check passes (row still looks un-revoked) but
    # a competing rotation already consumed it, so the guarded UPDATE matches 0 rows → reject.
    monkeypatch.setattr(service, "get_settings", _settings)
    raw, _jti = create_refresh_token("user-1", RKEY, 3600)
    row = _fresh_row(raw)

    class _RaceDb(_Db):
        def execute(self, stmt):
            if isinstance(stmt, Update):
                return _RowCount(0)  # lost the write race
            return super().execute(stmt)

    db = _RaceDb(row, SimpleNamespace(id="user-1", status=UserStatus.active))
    assert service.rotate_refresh(db, raw) is None
    assert db.committed is False  # no new pair issued when the write race is lost

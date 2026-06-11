"""A6 acceptance — runs against the live dev Aurora (skipped without DB env).

Proves: (1) both founders log in as owners of HoldSlot; (2) a second, ephemeral tenant
with a non-owner (member) user scopes correctly through the central guard — with NO schema
change. The ephemeral tenant + user are created and deleted inside the test; the build
still ships exactly one tenant.
"""

from __future__ import annotations

import os
import uuid

import pytest
from fastapi import HTTPException
from starlette.requests import Request

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)

BUILD_PW = "tryholdslot1!"
FOUNDERS = ["jason.tse@tryholdslot.com", "jason.wong@tryholdslot.com"]


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


def test_both_founders_login_as_owner():
    from fastapi.testclient import TestClient

    from app.main import app

    client = TestClient(app)
    for email in FOUNDERS:
        r = client.post("/auth/login", json={"email": email, "password": BUILD_PW})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        me = client.get("/me", headers=_auth(token)).json()
        assert any(c["slug"] == "holdslot" and c["role"] == "owner" for c in me["clients"])


def test_second_tenant_member_scopes_correctly():
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.deps import require_membership
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, Membership, MembershipRole, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug = f"acc-{suffix}"
    email = f"member-{suffix}@example.com"

    tenant = Tenant(slug=slug, name=f"Acceptance {suffix}")
    db.add(tenant)
    db.flush()
    member = AppUser(email=email, password_hash=hash_password(BUILD_PW), full_name="Member")
    db.add(member)
    db.flush()
    db.add(Membership(user_id=member.id, tenant_id=tenant.id, role=MembershipRole.member))
    db.commit()

    try:
        # Member logs in and sees ONLY their tenant, as member.
        r = client.post("/auth/login", json={"email": email, "password": BUILD_PW})
        assert r.status_code == 200, r.text
        token = r.json()["access_token"]
        me = client.get("/me", headers=_auth(token)).json()
        assert [(c["slug"], c["role"]) for c in me["clients"]] == [(slug, "member")]

        # Guard: member can read their own tenant context...
        ok = client.get(f"/{slug}/context", headers=_auth(token))
        assert ok.status_code == 200 and ok.json()["role"] == "member"

        # ...but is scoped OUT of HoldSlot (404, existence not leaked).
        assert client.get("/holdslot/context", headers=_auth(token)).status_code == 404

        # Role gate: an owner-only guard rejects the member (403) — no schema change needed.
        def _req(s: str) -> Request:
            return Request({"type": "http", "path_params": {"client": s}, "headers": []})

        owner_guard = require_membership(MembershipRole.owner)
        with pytest.raises(HTTPException) as exc:
            owner_guard(request=_req(slug), user=member, db=db)
        assert exc.value.status_code == 403
    finally:
        db.delete(member)  # membership cascades
        db.delete(tenant)
        db.commit()
        db.close()

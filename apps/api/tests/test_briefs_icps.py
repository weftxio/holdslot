"""B2 integration — brief + ICP document endpoints against the live dev Aurora.

Skipped without the DB env (like test_acceptance.py). Proves: JSONB round-trips opaquely
(including a key in no schema — the churn-proof guarantee), the brief upserts (one row per
client), ICP CRUD works, and the A4 guard scopes everything to the caller's tenant. All
rows are created under an ephemeral tenant and torn down — the build still ships one tenant.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)

BUILD_PW = "tryholdslot1!"


def _auth(token: str) -> dict[str, str]:
    return {"authorization": f"Bearer {token}"}


@pytest.fixture
def ephemeral_member():
    """An ephemeral tenant + member user; yields (client, slug, token); torn down after."""
    from fastapi.testclient import TestClient

    from app.core.db import get_session
    from app.core.security import hash_password
    from app.main import app
    from app.models import AppUser, Membership, MembershipRole, Tenant

    client = TestClient(app)
    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    slug = f"b2-{suffix}"
    email = f"b2-{suffix}@example.com"

    tenant = Tenant(slug=slug, name=f"B2 {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=email, password_hash=hash_password(BUILD_PW), full_name="B2 Member")
    db.add(user)
    db.flush()
    db.add(Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.member))
    db.commit()

    token = client.post("/auth/login", json={"email": email, "password": BUILD_PW}).json()[
        "access_token"
    ]
    try:
        yield client, slug, token
    finally:
        # Children (brief/icp) cascade via tenant_id ON DELETE CASCADE.
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()


def test_brief_roundtrips_opaque_json_and_upserts(ephemeral_member):
    client, slug, token = ephemeral_member

    # Empty to start.
    r = client.get(f"/{slug}/brief", headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"] == {} and r.json()["completeness"] == 0

    # PUT a doc INCLUDING a key in no schema — proves JSONB is opaque/churn-proof.
    doc = {
        "companyName": "Northwind",
        "valueProps": ["faster", "cheaper"],
        "a_field_no_schema_knows": {"nested": [1, 2, 3]},
    }
    r = client.put(f"/{slug}/brief", json={"data": doc}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["data"] == doc  # byte-for-byte round-trip
    assert 0 < r.json()["completeness"] < 100
    assert "companyName" not in r.json()["missing"]  # filled
    assert "website" in r.json()["missing"]  # still required + blank

    # Second PUT upserts (one row per client), not a duplicate.
    doc2 = {"companyName": "Acme"}
    r = client.put(f"/{slug}/brief", json={"data": doc2}, headers=_auth(token))
    assert r.json()["data"] == doc2
    assert client.get(f"/{slug}/brief", headers=_auth(token)).json()["data"] == doc2


def test_icp_crud(ephemeral_member):
    client, slug, token = ephemeral_member

    assert client.get(f"/{slug}/icps", headers=_auth(token)).json() == []

    a = client.post(
        f"/{slug}/icps",
        json={"name": "Ops leader", "tag": "primary", "data": {"seniority": ["VP"]}},
        headers=_auth(token),
    )
    assert a.status_code == 201, a.text
    b = client.post(
        f"/{slug}/icps",
        json={"name": "Champion", "tag": "", "data": {}},
        headers=_auth(token),
    )
    assert b.status_code == 201

    listed = client.get(f"/{slug}/icps", headers=_auth(token)).json()
    assert len(listed) == 2

    icp_id = a.json()["id"]
    u = client.put(
        f"/{slug}/icps/{icp_id}",
        json={
            "name": "Ops leader",
            "tag": "updated",
            "data": {"seniority": ["VP", "Director"]},
        },
        headers=_auth(token),
    )
    assert u.status_code == 200 and u.json()["tag"] == "updated"

    assert client.delete(f"/{slug}/icps/{icp_id}", headers=_auth(token)).status_code == 204
    assert len(client.get(f"/{slug}/icps", headers=_auth(token)).json()) == 1


def test_tenant_scoping_member_cannot_reach_holdslot(ephemeral_member):
    client, _slug, token = ephemeral_member
    # The member is scoped OUT of HoldSlot's brief + icps (404, existence not leaked).
    assert client.get("/holdslot/brief", headers=_auth(token)).status_code == 404
    assert client.get("/holdslot/icps", headers=_auth(token)).status_code == 404
    assert (
        client.put("/holdslot/brief", json={"data": {"x": 1}}, headers=_auth(token)).status_code
        == 404
    )

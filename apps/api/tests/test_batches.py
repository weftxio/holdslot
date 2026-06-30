"""Phase D (S3) tests — the masking allow-list + the one decision-write path.

The pure tests (no AWS, no DB) cover D's security core: `_masked` must never emit a clear-text
identity/contact vector, and `apply_decision` must write the right `prospect_approval` decisions.
The DB-gated acceptance test (skipped without the Aurora env) drives one real batch end-to-end —
create → send → masked external view → decide — the S3 "approved batch" proof.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.domains.approvals.router import _masked, _state
from app.domains.batches import service as svc

# --------------------------------------------------------------------------- pure: masking


def test_mask_name_first_plus_last_initial():
    assert svc.mask_name("Sarah Khan") == "Sarah K."
    assert svc.mask_name("  Sarah  Marie Khan ") == "Sarah K."
    assert svc.mask_name("Cher") == "Cher"
    assert svc.mask_name("") == ""
    assert svc.mask_name(None) == ""


def test_company_descriptor_firmographics_only():
    assert svc.company_descriptor("SaaS", "200-500", "US") == "SaaS · 200-500 · US"
    assert svc.company_descriptor("SaaS", None, "US") == "SaaS · US"
    assert svc.company_descriptor(None, None, None) == ""


def _fake_prospect():
    return SimpleNamespace(
        id=uuid.uuid4(),
        fit_tier="Strong",
        fit_reason="Active in your category; right seniority.",
        enrichment={
            "full_name": "Sarah Khan",
            "title": "VP Marketing",
            "seniority": "vp",
            "email": "sarah.khan@northwind.example",  # MUST NOT leak
            "linkedin_url": "https://linkedin.com/in/sarahkhan",  # MUST NOT leak
            "company": "Northwind Traders",  # exact name MUST NOT leak
            "domain": "northwind.example",  # exact domain MUST NOT leak
        },
        fit_components={"fit_reason": "x"},
    )


def test_masked_serializer_is_allow_list_no_clear_text():
    """The D4 security assertion: the serialized masked prospect contains the fit context and
    NOTHING that identifies or contacts the person — no email, phone, LinkedIn, full last name,
    exact company name, or domain."""
    p = _fake_prospect()
    company = SimpleNamespace(
        industry="SaaS", size="200-500", country="US",
        name="Northwind", domain="northwind.example",
    )
    approval = SimpleNamespace(id=uuid.uuid4(), decision="pending")

    out = _masked(approval, p, company)
    blob = json.dumps(out.model_dump())

    # present: fit context only
    assert out.name == "Sarah K."
    assert out.company_descriptor == "SaaS · 200-500 · US"
    assert out.title == "VP Marketing"
    assert out.fit_tier == "Strong"
    assert out.id == str(approval.id)

    # withheld: every clear-text identity/contact vector
    for leak in (
        "sarah.khan@northwind.example",
        "linkedin.com",
        "northwind.example",
        "Northwind",
        "Khan",  # full last name
    ):
        assert leak not in blob, f"masking leaked: {leak!r}"


def test_masked_serializer_falls_back_to_enrichment_descriptor_without_company():
    """A prospect with no linked `company` still masks cleanly off its enrichment firmographics —
    and still never emits the exact company name/domain."""
    p = _fake_prospect()
    p.enrichment["company_industry"] = "Logistics"
    p.enrichment["company_size"] = "1000+"
    out = _masked(SimpleNamespace(id=uuid.uuid4(), decision="pending"), p, None)
    assert out.company_descriptor == "Logistics · 1000+"
    assert "northwind.example" not in json.dumps(out.model_dump())


# --------------------------------------------------------------------------- pure: decision write


def _approvals(n: int):
    return [SimpleNamespace(id=uuid.uuid4(), decision="pending", decided_at=None) for _ in range(n)]


def test_apply_decision_approve_the_rest():
    batch = SimpleNamespace(status=svc.SENT, decided_at=None)
    a = _approvals(3)
    result = svc.apply_decision(batch, a, removed_ids=[str(a[1].id)])
    assert [x.decision for x in a] == ["approved", "removed", "approved"]
    assert result == {"approved": 2, "removed": 1}
    assert batch.status == svc.APPROVED_BATCH
    assert batch.decided_at is not None
    assert all(x.decided_at is not None for x in a)


def test_apply_decision_explicit_approved_ids_removes_others():
    batch = SimpleNamespace(status=svc.SENT, decided_at=None)
    a = _approvals(3)
    svc.apply_decision(batch, a, approved_ids=[str(a[0].id)])
    assert [x.decision for x in a] == ["approved", "removed", "removed"]


def test_apply_decision_removed_wins_over_approved():
    batch = SimpleNamespace(status=svc.SENT, decided_at=None)
    a = _approvals(2)
    svc.apply_decision(
        batch, a, approved_ids=[str(a[0].id), str(a[1].id)], removed_ids=[str(a[1].id)]
    )
    assert [x.decision for x in a] == ["approved", "removed"]


def test_apply_decision_request_changes_leaves_prospects_pending():
    batch = SimpleNamespace(status=svc.SENT, decided_at=None)
    a = _approvals(2)
    result = svc.apply_decision(batch, a, request_changes=True)
    assert batch.status == svc.CHANGES_REQUESTED
    assert [x.decision for x in a] == ["pending", "pending"]
    assert result == {"approved": 0, "removed": 0}


# --------------------------------------------------------------------------- pure: template + state


def test_template_default_and_render():
    tpl = svc.get_template_from({"subject": "Custom subject", "body": ""})
    assert tpl["subject"] == "Custom subject"
    assert tpl["body"] == svc.DEFAULT_TEMPLATE["body"]  # blank field falls back to default
    # {{prospects}} renders the count with a grammatical noun; no leftover tokens.
    one = svc.render_template(tpl, client_name="Northwind", count=1)
    assert "1 prospect " in one["body"] and "1 prospects" not in one["body"]
    assert "{{prospects}}" not in one["body"]
    many = svc.render_template(tpl, client_name="Northwind", count=12)
    assert "12 prospects" in many["body"]
    # {{client_name}} stays a supported token even though the default copy no longer uses it.
    custom = svc.render_template(
        {"subject": "", "body": "Hi {{client_name}}", "cta": ""}, client_name="Northwind", count=1
    )
    assert custom["body"] == "Hi Northwind" and "{{client_name}}" not in custom["body"]


def test_state_used_when_batch_decided_even_if_link_live():
    """A still-live link reads `used` once its batch is decided — the guard that stops a second
    Follow-Up link from double-deciding."""
    live_link = SimpleNamespace(used_at=None, expires_at=datetime.now(UTC) + timedelta(days=3))
    decided = SimpleNamespace(status=svc.APPROVED_BATCH)
    assert _state(live_link, decided) == "used"
    assert _state(live_link, SimpleNamespace(status=svc.SENT)) == "valid"
    expired = SimpleNamespace(used_at=None, expires_at=datetime.now(UTC) - timedelta(days=1))
    assert _state(expired, SimpleNamespace(status=svc.SENT)) == "expired"
    assert _state(live_link, None) == "expired"


# --------------------------------------------------------------------------- DB-gated: end-to-end

pytestmark_db = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)


@pytestmark_db
def test_batch_end_to_end_create_send_view_decide():
    """D6 acceptance — one real batch, end-to-end, against dev Aurora. Self-cleaning ephemeral
    tenant (mirrors test_acceptance): create → send (mints a link) → masked external view (no
    clear-text) → external decide → `prospect_approval` rows carry the decision; revisit reads used.
    """
    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.core.security import hash_token, new_opaque_token
    from app.domains.approvals.router import decide_approval, view_approval
    from app.domains.batches.router import create_batch, get_batch, send_approval
    from app.domains.batches.schemas import BatchCreateIn, DecisionIn, SendIn
    from app.models import (
        ApprovalLink,
        AppUser,
        Company,
        Membership,
        MembershipRole,
        Prospect,
        ProspectApproval,
        Tenant,
    )

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(slug=f"d-{suffix}", name=f"Northwind {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=f"owner-{suffix}@example.com", password_hash="x", full_name="Owner")
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner)
    db.add(membership)
    company = Company(
        tenant_id=tenant.id, domain="northwind.example", source="manual",
        name="Northwind Traders", industry="SaaS", size="200-500", country="US",
    )
    db.add(company)
    db.flush()
    prospects = []
    for i in range(2):
        p = Prospect(
            tenant_id=tenant.id, company_id=company.id, identity_key=f"d-{suffix}-{i}",
            source="manual", status="scored", fit_tier="Strong", fit_reason="great fit",
            enrichment={
                "full_name": f"Sarah Khan{i}", "title": "VP", "seniority": "vp",
                "email": f"sarah{i}@northwind.example", "linkedin_url": "https://linkedin.com/in/x",
                "company": "Northwind Traders", "domain": "northwind.example",
            },
        )
        db.add(p)
        prospects.append(p)
    db.commit()

    ctx = AccessContext(user=user, tenant=tenant, membership=membership)
    try:
        batch = create_batch(
            BatchCreateIn(prospect_ids=[str(p.id) for p in prospects]), ctx=ctx, db=db
        )
        assert batch.total == 2 and batch.status == "draft" and batch.pending == 2

        sent = send_approval(batch.id, SendIn(email="client@example.com"), ctx=ctx, db=db)
        assert sent.status == "sent" and sent.sent_at is not None
        assert db.query(ApprovalLink).filter_by(batch_id=uuid.UUID(batch.id)).count() == 1

        # Mint a known external token to drive the public surface (send stores only the hash).
        token = new_opaque_token()
        db.add(ApprovalLink(
            tenant_id=tenant.id, batch_id=uuid.UUID(batch.id), recipient_email="client@example.com",
            token_hash=hash_token(token), expires_at=datetime.now(UTC) + timedelta(days=7),
        ))
        db.commit()

        view = view_approval(token, db=db)
        assert view.state == "valid" and view.count == 2
        blob = json.dumps([p.model_dump() for p in view.prospects])
        assert "northwind.example" not in blob and "linkedin.com" not in blob
        assert view.prospects[0].name.endswith(".")  # masked

        first = view.prospects[0].id
        out = decide_approval(token, DecisionIn(removed_ids=[first]), db=db)
        assert out.status == "approved" and out.approved == 1 and out.removed == 1

        detail = get_batch(batch.id, ctx=ctx, db=db)
        assert detail.approved == 1 and detail.removed == 1
        assert view_approval(token, db=db).state == "used"  # single-use / batch decided
    finally:
        # children cascade from tenant; remove the link minted outside the batch FKs first
        db.query(ProspectApproval).filter_by(tenant_id=tenant.id).delete()
        db.query(ApprovalLink).filter_by(tenant_id=tenant.id).delete()
        db.commit()
        db.delete(membership)
        db.delete(user)
        db.delete(tenant)
        db.commit()
        db.close()


@pytestmark_db
def test_delete_batch_cascades_isolates_and_scopes():
    """Delete removes the batch + ALL its prospect_approval and approval_link rows by FK cascade, at
    any status (here an already-decided batch); a sibling batch's rows survive; a cross-tenant or
    missing id 404s and deletes nothing."""
    from fastapi import HTTPException

    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.batches.router import create_batch, decide_batch, delete_batch, send_approval
    from app.domains.batches.schemas import BatchCreateIn, DecisionIn, SendIn
    from app.models import (
        ApprovalLink,
        AppUser,
        Batch,
        Company,
        Membership,
        MembershipRole,
        Prospect,
        ProspectApproval,
        Tenant,
    )

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    tenant = Tenant(slug=f"del-{suffix}", name=f"Northwind {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=f"owner-{suffix}@example.com", password_hash="x", full_name="Owner")
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner)
    db.add(membership)
    company = Company(
        tenant_id=tenant.id, domain="northwind.example", source="manual",
        name="Northwind Traders", industry="SaaS", size="200-500", country="US",
    )
    db.add(company)
    db.flush()
    prospects = []
    for i in range(3):
        p = Prospect(
            tenant_id=tenant.id, company_id=company.id, identity_key=f"del-{suffix}-{i}",
            source="manual", status="scored", fit_tier="Strong", fit_reason="great fit",
            enrichment={"full_name": f"Sarah Khan{i}", "title": "VP"},
        )
        db.add(p)
        prospects.append(p)
    # second tenant — proves cross-tenant deletes are refused (404), not silently applied
    t2 = Tenant(slug=f"del2-{suffix}", name=f"Acme {suffix}")
    db.add(t2)
    db.flush()
    u2 = AppUser(email=f"owner2-{suffix}@example.com", password_hash="x", full_name="Owner2")
    db.add(u2)
    db.flush()
    m2 = Membership(user_id=u2.id, tenant_id=t2.id, role=MembershipRole.owner)
    db.add(m2)
    db.commit()

    ctx = AccessContext(user=user, tenant=tenant, membership=membership)
    ctx2 = AccessContext(user=u2, tenant=t2, membership=m2)
    try:
        # Batch A: send (mints a link) then decide → an *approved* batch carrying rows + a link.
        batch_a = create_batch(
            BatchCreateIn(prospect_ids=[str(prospects[0].id), str(prospects[1].id)]), ctx=ctx, db=db
        )
        bid_a = uuid.UUID(batch_a.id)
        send_approval(batch_a.id, SendIn(email="client@example.com"), ctx=ctx, db=db)
        decided = decide_batch(batch_a.id, DecisionIn(removed_ids=[]), ctx=ctx, db=db)
        assert decided.status == "approved"
        assert db.query(ProspectApproval).filter_by(batch_id=bid_a).count() == 2
        assert db.query(ApprovalLink).filter_by(batch_id=bid_a).count() == 1

        # Batch B: a sibling that must survive A's delete.
        batch_b = create_batch(BatchCreateIn(prospect_ids=[str(prospects[2].id)]), ctx=ctx, db=db)
        bid_b = uuid.UUID(batch_b.id)
        assert db.query(ProspectApproval).filter_by(batch_id=bid_b).count() == 1

        # Cross-tenant id (B owned by tenant 1, deleted as tenant 2) and a missing id both 404 —
        # and B is left intact.
        for bad_ctx, bad_id in ((ctx2, batch_b.id), (ctx, str(uuid.uuid4()))):
            with pytest.raises(HTTPException) as ei:
                delete_batch(bad_id, ctx=bad_ctx, db=db)
            assert ei.value.status_code == 404
        assert db.get(Batch, bid_b) is not None

        # Delete A (decided / any-status) → A and ALL its approval records + links are gone.
        assert delete_batch(batch_a.id, ctx=ctx, db=db) is None
        assert db.get(Batch, bid_a) is None
        assert db.query(ProspectApproval).filter_by(batch_id=bid_a).count() == 0
        assert db.query(ApprovalLink).filter_by(batch_id=bid_a).count() == 0

        # B untouched.
        assert db.get(Batch, bid_b) is not None
        assert db.query(ProspectApproval).filter_by(batch_id=bid_b).count() == 1
    finally:
        for tid in (tenant.id, t2.id):
            db.query(ProspectApproval).filter_by(tenant_id=tid).delete()
            db.query(ApprovalLink).filter_by(tenant_id=tid).delete()
        db.commit()
        db.delete(membership)
        db.delete(m2)
        db.delete(user)
        db.delete(u2)
        db.delete(tenant)
        db.delete(t2)
        db.commit()
        db.close()

"""Phase E integration — the launch worker + webhook ingest end-to-end against dev Aurora.

Skipped without the Aurora env (the D pattern). Self-cleaning ephemeral tenant. The Smartlead
adapter is fully mocked (no network, no send): the test proves OUR funnel logic — leads inserted
successful add, resume-the-gap idempotency, webhook dedupe + stage moves, and the unsub write-back —
not Smartlead's. The live send is proved separately by `scripts/e_smoke_live.py`.
"""

from __future__ import annotations

import os
import uuid

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)


class _FakeSmartlead:
    """A stand-in for the whole adapter — records calls, fabricates lead ids from the add payload.
    `accept` limits which emails the add-leads response returns (to exercise partial resume)."""

    def __init__(self, accept: set[str] | None = None):
        self.calls: list[str] = []
        self.accept = accept  # None = accept all
        self.next_id = 7000
        self.added: dict[str, int] = {}  # email → lead_id, served back via fetch_campaign_leads

    def install(self, monkeypatch, mods):
        fns = {
            "create_campaign": lambda name, client_id=None: {"ok": True, "id": 900123},
            "save_sequences": lambda cid, seqs: self.calls.append("save_sequences") or {"ok": True},
            "add_email_accounts": lambda cid, ids: self.calls.append("add_accounts") or {"ok": 1},
            "update_schedule": lambda cid, s: self.calls.append("schedule") or {"ok": True},
            "update_settings": lambda cid, s: self.calls.append("settings") or {"ok": True},
            "register_webhook": lambda cid, **k: self.calls.append("webhook") or {"ok": 1, "id": 1},
            "set_status": lambda cid, st: self.calls.append(f"status:{st}") or {"ok": True},
            "add_leads": self._add_leads,
            "fetch_campaign_leads": self._fetch_campaign_leads,
            "reply_to_thread": lambda cid, **k: self.calls.append("reply_thread") or {"ok": True},
            # sending-inbox ids now come from the `sending_account` table (seeded in _seed), not the
            # secret — so no `sending_account_ids` mock here.
            "webhook_path_token": lambda: "tok-abc",
        }
        for mod in mods:
            for name, fn in fns.items():
                monkeypatch.setattr(f"{mod}.sl.{name}", fn, raising=False)

    def _add_leads(self, cid, lead_list, settings=None):
        self.calls.append("add_leads")
        accepted = 0
        for lead in lead_list:
            email = lead["email"]
            if self.accept is not None and email.lower() not in self.accept:
                continue
            self.next_id += 1
            self.added[email.lower()] = self.next_id
            accepted += 1
        # Counts-only, like the live API — NO per-lead ids. The worker resolves ids via the roster.
        return {"ok": True, "upload_count": accepted, "total_leads": len(self.added),
                "block_count": 0, "duplicate_count": len(lead_list) - accepted}

    def _fetch_campaign_leads(self, cid, offset=0, limit=100):
        self.calls.append("fetch_leads")
        items = list(self.added.items())[offset : offset + limit]
        return {
            "total_leads": str(len(self.added)),
            "data": [{"lead": {"id": lid, "email": email}} for email, lid in items],
            "offset": offset,
            "limit": limit,
        }


def _seed(db, suffix, *, verified=2):
    from app.models import (
        AppUser,
        Batch,
        Brief,
        Company,
        Membership,
        MembershipRole,
        Prospect,
        ProspectApproval,
        SendingAccount,
        Tenant,
    )

    tenant = Tenant(slug=f"e-{suffix}", name=f"HoldSlot {suffix}")
    db.add(tenant)
    db.flush()
    # The launch worker reads the tenant's sending inboxes from the DB (not the secret) — seed two
    # active rows so `_do_launch` resolves accounts. Per-tenant unique, so a fixed 11/22 is safe
    # across parallel ephemeral tenants.
    db.add(SendingAccount(tenant_id=tenant.id, smartlead_account_id=11, status="active"))
    db.add(SendingAccount(tenant_id=tenant.id, smartlead_account_id=22, status="active"))
    user = AppUser(email=f"e-{suffix}@example.com", password_hash="x", full_name="Owner")
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner)
    db.add(membership)
    db.add(Brief(tenant_id=tenant.id, data={"doNotContact": ""}))
    company = Company(
        tenant_id=tenant.id, domain="northwind.example", source="manual", name="Northwind",
        industry="SaaS", size="200-500", country="US",
    )
    db.add(company)
    db.flush()
    batch = Batch(tenant_id=tenant.id, name="Batch 1", status="approved", icp_id=None)
    db.add(batch)
    db.flush()
    prospects = []
    for i in range(2):
        p = Prospect(
            tenant_id=tenant.id, company_id=company.id, identity_key=f"e-{suffix}-{i}",
            source="manual", status="scored", email_valid=(i < verified),
            enrichment={
                "full_name": f"Dana Reyes{i}", "first_name": "Dana", "last_name": f"Reyes{i}",
                "title": "VP Ops", "email": f"dana{i}@northwind.example", "company": "Northwind",
            },
        )
        db.add(p)
        db.flush()
        db.add(
            ProspectApproval(
                tenant_id=tenant.id, batch_id=batch.id, prospect_id=p.id, decision="approved"
            )
        )
        prospects.append(p)
    db.commit()
    return tenant, user, membership, batch, prospects


def _run_launch(db, tenant_id, campaign_id):
    """Claim (draft/sending → launching) then run the worker synchronously off a fresh session."""
    from app.core.db import get_session
    from app.domains.campaigns import launch
    from app.models import Campaign

    camp = db.get(Campaign, uuid.UUID(str(campaign_id)))
    assert launch.claim_for_launch(db, camp)
    launch.run_launch_job(tenant_id, campaign_id, session_factory=get_session)
    db.expire_all()  # our session must re-read what the worker's session committed


def _teardown(db, tenant, membership, user):
    from app.models import (
        Campaign,
        CampaignLead,
        OutreachEvent,
        ProspectApproval,
        SendingAccount,
    )

    tid = tenant.id
    db.query(OutreachEvent).filter_by(tenant_id=tid).delete()
    db.query(CampaignLead).filter_by(tenant_id=tid).delete()
    db.query(Campaign).filter_by(tenant_id=tid).delete()
    db.query(ProspectApproval).filter_by(tenant_id=tid).delete()
    db.query(SendingAccount).filter_by(tenant_id=tid).delete()
    db.commit()
    db.delete(membership)
    db.delete(user)
    db.delete(tenant)
    db.commit()
    db.close()


def test_create_launch_and_webhook_funnel(monkeypatch):
    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.campaigns import webhooks
    from app.domains.campaigns.router import create_campaign, get_campaign
    from app.domains.campaigns.schemas import CampaignCreateIn, VariantIn
    from app.models import Brief, Campaign, CampaignLead, OutreachEvent

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    tenant, user, membership, batch, prospects = _seed(db, suffix)
    fake = _FakeSmartlead()
    fake.install(monkeypatch, ["app.domains.campaigns.launch", "app.domains.campaigns.webhooks"])
    ctx = AccessContext(user=user, tenant=tenant, membership=membership)
    try:
        # --- E3 create (approved batch) + idempotency ---
        created = create_campaign(
            CampaignCreateIn(
                batch_id=str(batch.id),
                variants=[VariantIn(key="A", subject="Hi {{company_name}}", body="one line")],
            ),
            ctx=ctx,
            db=db,
        )
        assert created.status == "draft" and len(created.variants) == 1
        again = create_campaign(CampaignCreateIn(batch_id=str(batch.id)), ctx=ctx, db=db)
        assert again.id == created.id  # idempotent on batch_id

        # --- E3 launch worker (Smartlead mocked) ---
        _run_launch(db, tenant.id, created.id)
        detail = get_campaign(created.id, ctx=ctx, db=db)
        assert detail.status == "sending"
        assert detail.stages.get("contacted") == 2  # both verified leads inserted @ contacted
        leads = (
            db.query(CampaignLead)
            .filter_by(campaign_id=uuid.UUID(created.id))
            .order_by(CampaignLead.created_at)
            .all()
        )
        assert all(lead.smartlead_lead_id for lead in leads)
        sl_campaign_id = detail.smartlead_campaign_id
        assert "status:START" in fake.calls
        lead0, lead1 = leads[0], leads[1]

        # --- E4 email_sent seq2 → followup (resolved by the real webhook field sl_email_lead_id) --
        # M8 — the send event carries the per-lead A/B/C `variant_label`; the ingest stamps it onto
        # the lead so the E6 scoreboard (derived from campaign_lead.variant_key) shows real counts.
        webhooks._ingest(db, {
            "event_type": "EMAIL_SENT", "campaign_id": sl_campaign_id,
            "sl_email_lead_id": lead0.smartlead_lead_id, "sequence_number": 2,
            "variant_label": "A",
            "to_email": lead0_email(prospects, lead0), "event_timestamp": "2026-07-13T09:00:00Z",
        })
        db.refresh(lead0)
        assert lead0.stage == "followup"
        assert lead0.variant_key == "A"  # M8 — variant stamped from the send event

        # --- E4 reply → queue row (triage NULL, stage unchanged) + dedupe ---
        reply = {
            "event_type": "EMAIL_REPLY", "campaign_id": sl_campaign_id,
            "lead_id": lead0.smartlead_lead_id, "from_email": lead0_email(prospects, lead0),
            "to_email": "outreach@getholdslot.com", "reply_body": "Sure, Thursday works",
            "time_replied": "2026-07-13T14:00:00Z",
        }
        webhooks._ingest(db, reply)
        webhooks._ingest(db, dict(reply))  # identical retry → dedupe
        replies = db.query(OutreachEvent).filter_by(
            campaign_id=uuid.UUID(created.id), event_type="lead_replied"
        ).all()
        assert len(replies) == 1  # deduped
        db.refresh(lead0)
        assert lead0.stage == "followup"  # a reply does NOT auto-advance

        # --- E4 unsubscribe → drop + doNotContact write-back ---
        webhooks._ingest(db, {
            "event_type": "LEAD_UNSUBSCRIBED", "campaign_id": sl_campaign_id,
            "lead_id": lead1.smartlead_lead_id, "to_email": prospects[1].enrichment["email"],
            "event_timestamp": "2026-07-13T15:00:00Z",
        })
        db.refresh(lead1)
        assert lead1.stage == "drop"
        brief = db.query(Brief).filter_by(tenant_id=tenant.id).one()
        assert prospects[1].enrichment["email"] in str(brief.data.get("doNotContact"))

        # --- M3 — an unsubscribe with NO resolvable lead (and hence no stage move) still writes
        # doNotContact: the SG-PDPA honor is independent of the stage effect (the old code nested
        # the write-back under the move, so an unresolvable/already-dropped unsub silently skipped
        # the list). Same-campaign, an email matching no lead → campaign_lead_id NULL, DNC written.
        webhooks._ingest(db, {
            "event_type": "LEAD_UNSUBSCRIBED", "campaign_id": sl_campaign_id,
            "to_email": "ghost@nowhere.example", "event_timestamp": "2026-07-13T16:00:00Z",
        })
        brief = db.query(Brief).filter_by(tenant_id=tenant.id).one()
        assert "ghost@nowhere.example" in str(brief.data.get("doNotContact"))

        # --- E4 unknown campaign → ignored, no crash ---
        out = webhooks._ingest(db, {"event_type": "EMAIL_SENT", "campaign_id": "999999999"})
        assert out.get("ignored") == "unknown campaign"

        # --- E5 reply queue: list (pip), triage positive → replied, respond → threaded send ---
        from app.domains.campaigns.router import list_replies, respond_reply, triage_reply
        from app.domains.campaigns.schemas import RespondIn, TriageIn

        open_replies = list_replies(state="open", ctx=ctx, db=db)
        assert len(open_replies) == 1  # the one un-handled reply (lead0)
        reply_id = open_replies[0].id

        triaged = triage_reply(reply_id, TriageIn(triage="positive"), ctx=ctx, db=db)
        assert triaged.triage == "positive" and triaged.handled_at is not None
        db.refresh(lead0)
        assert lead0.stage == "replied"  # positive triage advanced followup → replied
        assert list_replies(state="open", ctx=ctx, db=db) == []  # pip cleared

        # respond — the documented reply payload has no handle, so the master-inbox recovery runs;
        # stub it to return one, then the threaded send fires and a reply_sent row lands.
        monkeypatch.setattr(
            "app.domains.campaigns.router.sl.fetch_inbox_replies",
            lambda cid, **k: {"data": [{"from_email": prospects[0].enrichment["email"],
                                        "stats_id": "st-1", "message_id": "<m-1>"}]},
        )
        responded = respond_reply(
            reply_id, RespondIn(body="Thursday 2pm works — sending a link."), ctx=ctx, db=db
        )
        assert responded.response_body.startswith("Thursday")
        assert "reply_thread" in fake.calls
        sent = db.query(OutreachEvent).filter_by(
            campaign_id=uuid.UUID(created.id), event_type="reply_sent"
        ).count()
        assert sent == 1

        # --- E6 controls: winner toggle, pause/resume, statistics sync ---
        from app.domains.campaigns.router import (
            pause_campaign,
            resume_campaign,
            set_variant_winner,
            sync_campaign,
        )
        from app.domains.campaigns.schemas import WinnerIn

        won = set_variant_winner(created.id, WinnerIn(key="A"), ctx=ctx, db=db)
        assert next(v for v in won.variants if v.key == "A").is_winner is True

        paused = pause_campaign(created.id, ctx=ctx, db=db)
        assert paused.status == "paused" and "status:PAUSED" in fake.calls
        resumed = resume_campaign(created.id, ctx=ctx, db=db)
        assert resumed.status == "sending"

        # sync poll — no lead is at `contacted` here, so it's a clean no-op read (drift logic is
        # unit-tested in test_campaigns.py::test_parse_statistics_progress...).
        monkeypatch.setattr(
            "app.domains.campaigns.router.sl.fetch_statistics", lambda cid, **k: {"data": []}
        )
        synced = sync_campaign(created.id, ctx=ctx, db=db)
        assert synced.status == "sending"

        assert isinstance(db.get(Campaign, uuid.UUID(created.id)), Campaign)
    finally:
        _teardown(db, tenant, membership, user)


def lead0_email(prospects, lead):
    """The prospect email behind a lead row (matched by prospect_id)."""
    return next(p.enrichment["email"] for p in prospects if p.id == lead.prospect_id)


def test_launch_resumes_only_the_gap(monkeypatch):
    """Partial failure: the first add accepts only 1 of 2 leads → 1 campaign_lead. A re-launch
    (both now accepted) pushes ONLY the missing lead — never a duplicate."""
    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.campaigns.router import create_campaign
    from app.domains.campaigns.schemas import CampaignCreateIn
    from app.models import CampaignLead

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    tenant, user, membership, batch, prospects = _seed(db, suffix)
    ctx = AccessContext(user=user, tenant=tenant, membership=membership)
    try:
        created = create_campaign(CampaignCreateIn(batch_id=str(batch.id)), ctx=ctx, db=db)
        # first launch accepts only dana0
        _FakeSmartlead(accept={"dana0@northwind.example"}).install(
            monkeypatch, ["app.domains.campaigns.launch"]
        )
        _run_launch(db, tenant.id, created.id)
        n1 = db.query(CampaignLead).filter_by(campaign_id=uuid.UUID(created.id)).count()
        assert n1 == 1  # only the accepted lead was inserted

        # re-launch (from sending), now accept both — only the gap (dana1) is pushed
        _FakeSmartlead(accept={"dana0@northwind.example", "dana1@northwind.example"}).install(
            monkeypatch, ["app.domains.campaigns.launch"]
        )
        _run_launch(db, tenant.id, created.id)
        n2 = db.query(CampaignLead).filter_by(campaign_id=uuid.UUID(created.id)).count()
        assert n2 == 2  # exactly the missing lead added — no duplicate for dana0
    finally:
        _teardown(db, tenant, membership, user)

"""Phase F integration — booking → sweep → reads → feedback end-to-end against dev Aurora.

Skipped without the Aurora env (the D/E pattern). Self-cleaning ephemeral tenant. Google + Smartlead
+ SES are fully mocked (no network, no send, no spend): the test proves OUR money logic — the atomic
single-use claim, claim-release on a Google failure, the approval snapshot, the idempotent qualify
sweep, and the derived reads — not Google's. The live contract is proved separately by
`scripts/f_smoke_live.py`.

Covers the DB-flow money cases the register lists under F3/F4/F5 (FT3-10/11/13/15, FT4-3/10, FTI)
that need a real DB (the codebase has no non-Aurora DB harness; the pure branches live in
`test_meetings.py`).
"""

from __future__ import annotations

import os
import re
import uuid
from datetime import UTC, datetime, timedelta

import pytest

pytestmark = pytest.mark.skipif(
    not os.environ.get("HOLDSLOT_DB_CLUSTER_ARN"),
    reason="integration test — needs Aurora dev env (HOLDSLOT_DB_* + AWS creds)",
)

# An availability doc with all-day windows every weekday so a bookable slot ≥24h out always exists.
_AVAIL = {
    "availability": {
        "tz": "UTC",
        "meeting_minutes": 30,
        "windows": {d: [["00:00", "23:30"]] for d in ("mon", "tue", "wed", "thu", "fri")},
    },
    "attendee_email": "client@acme.example",
}


class _FakeGoogle:
    """Stand-in for the whole Google adapter — records create_event calls, serves canned records."""

    def __init__(self):
        self.busy: list[dict] = []
        self.records: list[dict] = []
        self.participants: list[dict] = []
        self.create_error = False
        self.busy_error = False  # M2 — simulate a free/busy outage
        self.created: list[dict] = []

    def install(self, monkeypatch):
        import app.integrations.google.client as g

        monkeypatch.setattr(g, "freebusy", self._freebusy)
        monkeypatch.setattr(g, "create_event", self._create)
        monkeypatch.setattr(g, "list_conference_records", lambda code: list(self.records))
        monkeypatch.setattr(g, "list_participants", lambda rid: list(self.participants))

    def _freebusy(self, tmin, tmax, **k):
        import app.integrations.google.client as g

        if self.busy_error:
            raise g.GoogleError("freebusy outage")
        return list(self.busy)

    def _create(self, **kw):
        import app.integrations.google.client as g

        if self.create_error:
            raise g.GoogleError("boom")
        self.created.append(kw)
        return {
            "id": "evt_test",
            "hangoutLink": "https://meet.google.com/abc-defg-hij",
            "conferenceData": {
                "conferenceId": "abc-defg-hij",
                "status": {"statusCode": "success"},
            },
        }


def _seed(db, suffix):
    from app.models import (
        AppUser,
        Batch,
        Brief,
        Campaign,
        CampaignLead,
        Company,
        Membership,
        MembershipRole,
        OutreachEvent,
        Prospect,
        ProspectApproval,
        Tenant,
    )

    tenant = Tenant(slug=f"f-{suffix}", name=f"HoldSlot {suffix}")
    db.add(tenant)
    db.flush()
    user = AppUser(email=f"f-{suffix}@example.com", password_hash="x", full_name="Owner")
    db.add(user)
    db.flush()
    membership = Membership(user_id=user.id, tenant_id=tenant.id, role=MembershipRole.owner)
    db.add(membership)
    db.add(Brief(tenant_id=tenant.id, data=_AVAIL))
    company = Company(
        tenant_id=tenant.id,
        domain="acme.example",
        source="manual",
        name="Acme",
        industry="SaaS",
        size="200-500",
        country="US",
    )
    db.add(company)
    db.flush()
    prospect = Prospect(
        tenant_id=tenant.id,
        company_id=company.id,
        identity_key=f"f-{suffix}",
        source="manual",
        status="scored",
        email_valid=True,
        enrichment={
            "full_name": "Dana Reyes",
            "first_name": "Dana",
            "title": "VP Ops",
            "email": "dana@acme.example",
            "company": "Acme",
        },
    )
    db.add(prospect)
    db.flush()
    batch = Batch(tenant_id=tenant.id, name="Batch 1", status="approved", icp_id=None)
    db.add(batch)
    db.flush()
    approval = ProspectApproval(
        tenant_id=tenant.id, batch_id=batch.id, prospect_id=prospect.id, decision="approved"
    )
    db.add(approval)
    db.flush()
    campaign = Campaign(
        tenant_id=tenant.id,
        batch_id=batch.id,
        name="Campaign 1",
        status="sending",
        smartlead_campaign_id="900123",
    )
    db.add(campaign)
    db.flush()
    lead = CampaignLead(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        prospect_id=prospect.id,
        approval_id=approval.id,
        stage="replied",
        smartlead_lead_id="7001",
    )
    db.add(lead)
    db.flush()
    reply = OutreachEvent(
        tenant_id=tenant.id,
        campaign_id=campaign.id,
        campaign_lead_id=lead.id,
        event_type="lead_replied",
        payload={
            "stats_id": "S1",
            "message_id": "M1",
            "reply_body": "interested",
            "subject": "Re: hi",
        },
    )
    db.add(reply)
    db.commit()
    return {
        "tenant": tenant,
        "user": user,
        "membership": membership,
        "batch": batch,
        "campaign": campaign,
        "lead": lead,
        "approval": approval,
        "prospect": prospect,
        "reply": reply,
    }


def _teardown(db, s):
    from app.models import (
        BookingLink,
        Campaign,
        CampaignLead,
        FeedbackLink,
        Meeting,
        OutreachEvent,
        ProspectApproval,
    )

    tid = s["tenant"].id
    db.query(FeedbackLink).filter_by(tenant_id=tid).delete()
    db.query(Meeting).filter_by(tenant_id=tid).delete()
    db.query(BookingLink).filter_by(tenant_id=tid).delete()
    db.query(OutreachEvent).filter_by(tenant_id=tid).delete()
    db.query(CampaignLead).filter_by(tenant_id=tid).delete()
    db.query(Campaign).filter_by(tenant_id=tid).delete()
    db.query(ProspectApproval).filter_by(tenant_id=tid).delete()
    db.commit()
    from app.models import Batch, Brief, Company, Prospect

    db.query(Prospect).filter_by(tenant_id=tid).delete()
    db.query(Company).filter_by(tenant_id=tid).delete()
    db.query(Batch).filter_by(tenant_id=tid).delete()
    db.query(Brief).filter_by(tenant_id=tid).delete()
    db.commit()
    db.delete(s["membership"])
    db.delete(s["user"])
    db.delete(s["tenant"])
    db.commit()
    db.close()


def test_freebusy_outage_offers_no_slots_and_503_releases(monkeypatch):
    """M2 — a Google free/busy outage must never confirm a booking blind: `view_booking` offers NO
    slots (not the full grid) and `book_meeting` 503s + RELEASES the single-use claim so the
    prospect can retry once Google recovers (FT3-9 / FD-6)."""
    from fastapi import HTTPException

    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.meetings import public
    from app.domains.meetings.schemas import BookIn
    from app.models import BookingLink

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    s = _seed(db, suffix)
    ctx = AccessContext(user=s["user"], tenant=s["tenant"], membership=s["membership"])
    fake = _FakeGoogle()
    fake.install(monkeypatch)
    try:
        token = _respond_with_link(db, s, ctx, monkeypatch)
        # A healthy read first — grab a real grid slot to POST during the outage.
        healthy = public.view_booking(token, db=db)
        assert healthy.state == "valid" and healthy.slots
        slot = healthy.slots[0]

        # Outage: the view offers no slots at all (the old []-return offered the full grid).
        fake.busy_error = True
        outage_view = public.view_booking(token, db=db)
        assert outage_view.state == "valid" and outage_view.slots == []

        # A POST during the outage 503s and releases the claim (used_at back to NULL).
        with pytest.raises(HTTPException) as ei:
            public.book_meeting(token, BookIn(slot=slot), db=db)
        assert ei.value.status_code == 503
        link = db.query(BookingLink).filter_by(tenant_id=s["tenant"].id).one()
        assert link.used_at is None  # released for retry — never left claimed on an outage
    finally:
        _teardown(db, s)


def _respond_with_link(db, s, ctx, monkeypatch):
    """Send a reply with a booking link (Smartlead mocked) → return the raw booking token."""
    from app.domains.campaigns import router as crouter
    from app.domains.campaigns.schemas import RespondIn

    monkeypatch.setattr(crouter.sl, "reply_to_thread", lambda cid, **k: {"ok": True})
    out = crouter.respond_reply(
        str(s["reply"].id),
        RespondIn(body="Pick a time: {{booking_link}}", include_booking_link=True),
        ctx=ctx,
        db=db,
    )
    token = re.search(r"/book/([A-Za-z0-9_-]+)", out.response_body).group(1)
    return token


def test_full_booking_sweep_reads_feedback(monkeypatch):
    """FTI-1/2/3 + FT3-13 + FT4-3/10 — the whole loop: respond+link → book → sweep-qualify → reads →
    feedback, with the approval snapshot + idempotent sweep asserted."""
    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.meetings import public, router
    from app.domains.meetings.schemas import BookIn, FeedbackIn
    from app.models import BookingLink, Meeting

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    s = _seed(db, suffix)
    ctx = AccessContext(user=s["user"], tenant=s["tenant"], membership=s["membership"])
    fake = _FakeGoogle()
    fake.install(monkeypatch)
    try:
        # --- FTI-1: respond + link → GET book (slots) → POST book (meeting + stage) ---
        token = _respond_with_link(db, s, ctx, monkeypatch)
        link = db.query(BookingLink).filter_by(tenant_id=s["tenant"].id).one()
        assert link.used_at is None

        view = public.view_booking(token, db=db)
        assert view.state == "valid" and view.slots
        slot = view.slots[0]

        confirm = public.book_meeting(token, BookIn(slot=slot), db=db)
        assert confirm.state == "confirmed"
        meeting = db.query(Meeting).filter_by(tenant_id=s["tenant"].id).one()
        # S3 — meet_link is no longer echoed in the confirm body; it's persisted on the row.
        assert meeting.meet_link.endswith("abc-defg-hij")
        # FT3-13 — the approval snapshot + the ids off the response.
        assert meeting.approval_id == s["approval"].id
        assert meeting.google_event_id == "evt_test"
        db.refresh(s["lead"])
        assert s["lead"].stage == "meeting"  # advanced via the booking claim

        # --- FTI-2 / FT4-3: nudge into the past, sweep with a qualified record ---
        meeting.scheduled_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()
        fake.records = [
            {
                "name": "conferenceRecords/rec1",
                "startTime": "2026-07-15T10:00:00Z",
                "endTime": "2026-07-15T10:47:00Z",
            }
        ]
        fake.participants = [
            {"earliestStartTime": "2026-07-15T10:00:05Z", "latestEndTime": "2026-07-15T10:47:00Z"},
            {"earliestStartTime": "2026-07-15T10:01:00Z", "latestEndTime": "2026-07-15T10:45:00Z"},
        ]
        res = router.sweep_meetings(db, s["tenant"].id)
        assert res.qualified == 1
        db.refresh(meeting)
        assert meeting.held is True and meeting.outcome == "qualified"
        assert float(meeting.amount) == 500 and meeting.duration_min == 47
        db.refresh(s["lead"])
        assert s["lead"].stage == "billable"

        # FT4-10 — a second sweep changes nothing (the WHERE held IS NULL claim).
        before = (meeting.held, meeting.outcome, float(meeting.amount))
        router.sweep_meetings(db, s["tenant"].id)
        db.refresh(meeting)
        assert (meeting.held, meeting.outcome, float(meeting.amount)) == before

        # --- reads render the row ---
        ledger = router.list_meetings(when="past", ctx=ctx, db=db)
        assert len(ledger) == 1 and ledger[0].billing_chip in ("Held", "Billed")
        bookings = router.list_bookings(ctx=ctx, db=db)
        assert bookings[0].status == "Confirmed"
        feedback_rows = router.list_feedback(ctx=ctx, db=db)
        assert len(feedback_rows) == 1 and feedback_rows[0].state == "None"

        # --- FTI-3: feedback-send (SES mocked) → public GET/POST → rating lands; 2nd POST 410 ---
        sent: list = []
        monkeypatch.setattr(router, "send_email", lambda to, subj, body: sent.append(body) or True)
        router.send_feedback(str(meeting.id), ctx=ctx, db=db)
        ftoken = re.search(r"/feedback/([A-Za-z0-9_-]+)", sent[0]).group(1)
        assert public.view_feedback(ftoken, db=db).state == "valid"
        public.submit_feedback(
            ftoken, FeedbackIn(rating=4, chips=["Prepared"], comment="great"), db=db
        )
        db.refresh(meeting)
        assert meeting.feedback_rating == 4 and meeting.feedback_at is not None
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as ei:
            public.submit_feedback(ftoken, FeedbackIn(rating=5), db=db)
        assert ei.value.status_code == 410  # single-use
    finally:
        _teardown(db, s)


def test_claim_atomicity_and_release(monkeypatch):
    """FT3-10/11/15 — the money claim: double-book 410, Google-fail release+503, tampered 400."""
    from fastapi import HTTPException

    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.meetings import public
    from app.domains.meetings.schemas import BookIn
    from app.models import BookingLink, Meeting

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    s = _seed(db, suffix)
    ctx = AccessContext(user=s["user"], tenant=s["tenant"], membership=s["membership"])
    fake = _FakeGoogle()
    fake.install(monkeypatch)
    try:
        token = _respond_with_link(db, s, ctx, monkeypatch)
        slot = public.view_booking(token, db=db).slots[0]

        # FT3-15 — a tampered slot (year in the past, off-grid) → 400, claim released, no meeting.
        with pytest.raises(HTTPException) as ei:
            public.book_meeting(token, BookIn(slot="2020-01-01T00:00:00Z"), db=db)
        assert ei.value.status_code == 400
        db.expire_all()
        assert db.query(BookingLink).filter_by(id=_bl_id(db, s)).one().used_at is None
        assert db.query(Meeting).filter_by(tenant_id=s["tenant"].id).count() == 0

        # FT3-11 — Google hard-fail after the claim → used_at released + 503 → a retry succeeds.
        fake.create_error = True
        with pytest.raises(HTTPException) as ei:
            public.book_meeting(token, BookIn(slot=slot), db=db)
        assert ei.value.status_code == 503
        db.expire_all()
        assert db.query(BookingLink).filter_by(id=_bl_id(db, s)).one().used_at is None
        fake.create_error = False
        confirm = public.book_meeting(token, BookIn(slot=slot), db=db)
        assert confirm.state == "confirmed"
        assert db.query(Meeting).filter_by(tenant_id=s["tenant"].id).count() == 1

        # FT3-10 — a second POST on the now-used token → 410, still exactly one meeting.
        with pytest.raises(HTTPException) as ei:
            public.book_meeting(token, BookIn(slot=slot), db=db)
        assert ei.value.status_code == 410
        assert db.query(Meeting).filter_by(tenant_id=s["tenant"].id).count() == 1
    finally:
        _teardown(db, s)


def test_won_door_isolates_billing():
    """NF-3 — the dedicated `won` setter writes ONLY `won`. A qualified/billed meeting's outcome,
    amount, dispute window, disputed flag and held state are all untouched (billing isolation), and
    a `null` write clears the flag without moving the billing decision either."""
    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.meetings import router
    from app.domains.meetings.schemas import WonIn
    from app.models import Meeting

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    s = _seed(db, suffix)
    ctx = AccessContext(user=s["user"], tenant=s["tenant"], membership=s["membership"])
    try:
        meeting = Meeting(
            tenant_id=s["tenant"].id,
            campaign_lead_id=s["lead"].id,
            prospect_id=s["prospect"].id,
            approval_id=s["approval"].id,
            scheduled_at=datetime.now(UTC) - timedelta(hours=2),
            held=True,
            duration_min=30,
            outcome="qualified",
            amount=500,
            dispute_window_ends_at=datetime.now(UTC) + timedelta(hours=48),
            disputed=False,
            won=None,
        )
        db.add(meeting)
        db.commit()
        billing_before = (
            meeting.outcome,
            float(meeting.amount),
            meeting.dispute_window_ends_at,
            meeting.disputed,
            meeting.held,
        )

        out = router.set_won(str(meeting.id), WonIn(won=True), ctx=ctx, db=db)
        db.refresh(meeting)
        assert meeting.won is True and out.won is True
        assert (
            meeting.outcome,
            float(meeting.amount),
            meeting.dispute_window_ends_at,
            meeting.disputed,
            meeting.held,
        ) == billing_before
        assert out.billing_chip in ("Held", "Billed")  # the billing decision is preserved

        # null clears the flag back to undecided — still no billing movement.
        router.set_won(str(meeting.id), WonIn(won=None), ctx=ctx, db=db)
        db.refresh(meeting)
        assert meeting.won is None
        assert float(meeting.amount) == 500 and meeting.outcome == "qualified"
    finally:
        _teardown(db, s)


def test_correct_outcome_blocks_unswept_future_meeting():
    """M18 — a correction must never bill a meeting that hasn't happened. An unswept future meeting
    (held IS NULL, scheduled in the future) → 409 with nothing stamped; once it is past (or swept),
    the same correction is allowed and stamps the amount."""
    from fastapi import HTTPException

    from app.core.db import get_session
    from app.core.deps import AccessContext
    from app.domains.meetings import router
    from app.domains.meetings.schemas import OutcomeIn
    from app.models import Meeting

    db = get_session()
    suffix = uuid.uuid4().hex[:8]
    s = _seed(db, suffix)
    ctx = AccessContext(user=s["user"], tenant=s["tenant"], membership=s["membership"])
    try:
        meeting = Meeting(
            tenant_id=s["tenant"].id,
            campaign_lead_id=s["lead"].id,
            prospect_id=s["prospect"].id,
            approval_id=s["approval"].id,
            scheduled_at=datetime.now(UTC) + timedelta(days=2),  # future
            held=None,  # unswept
        )
        db.add(meeting)
        db.commit()

        with pytest.raises(HTTPException) as ei:
            router.correct_outcome(str(meeting.id), OutcomeIn(outcome="qualified"), ctx=ctx, db=db)
        assert ei.value.status_code == 409
        db.refresh(meeting)
        assert meeting.outcome is None and meeting.amount is None  # nothing stamped

        # once the meeting is in the past, the correction is legitimate and stamps the amount.
        meeting.scheduled_at = datetime.now(UTC) - timedelta(hours=2)
        db.commit()
        out = router.correct_outcome(
            str(meeting.id), OutcomeIn(outcome="qualified"), ctx=ctx, db=db
        )
        assert out.outcome == "qualified" and out.amount == 500
    finally:
        _teardown(db, s)


def _bl_id(db, s):
    from app.models import BookingLink

    return db.query(BookingLink).filter_by(tenant_id=s["tenant"].id).one().id

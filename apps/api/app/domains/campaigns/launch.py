"""Async campaign launch (E3) — build the Smartlead campaign + push the approved batch, off the
30 s gateway path.

Reuses the `scoring_job` machinery WITHOUT a new job table: **`campaign.status = 'launching'` IS the
job state.** `enqueue_launch` atomically claims the campaign (draft/error/sending → launching) and
self-invokes the Lambda; the worker builds the Smartlead campaign, adds the approved+verified leads
(inserting a `campaign_lead` @ `contacted` only as each add succeeds — the funnel never shows an
unsent lead), and flips `sending`. A worker hard-killed by the Lambda timeout leaves `launching`
forever, so on read a `launching` campaign older than `MAX_JOB_AGE_SECONDS` (the shared scoring
constant) is reaped → `error`. **Re-launch resumes idempotently:** the Smartlead campaign is created
once (id stored), setup steps gate on a `settings` flag, and only prospects lacking a
`campaign_lead` are pushed — so a partial failure + retry pushes exactly the gap.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.domains.campaigns import service as svc
from app.domains.prospects.scoring import MAX_JOB_AGE_SECONDS
from app.integrations.smartlead import client as sl
from app.models import (
    Campaign,
    CampaignLead,
    OutreachEvent,
    Prospect,
    ProspectApproval,
    SendingAccount,
)

log = logging.getLogger("holdslot.campaign.launch")

# Background-job event contract (shares the key app.main.handler routes; the VALUE selects us).
JOB_EVENT_KEY = "holdslot_job"
JOB_CAMPAIGN_LAUNCH = "campaign_launch"

# campaign.status lifecycle.
DRAFT = "draft"
LAUNCHING = "launching"
SENDING = "sending"
PAUSED = "paused"
COMPLETED = "completed"
ERROR = "error"
# A launch (or re-launch/resume) may start from any of these; `launching` is in-flight (409).
LAUNCHABLE = (DRAFT, ERROR, SENDING)

DEFAULT_DAILY_CAP = 40  # EF-Q3 warm-up ceiling
_ERR_MAX = 500
ACTIVE_ACCOUNT = "active"  # sending_account.status — only `active` inboxes are attached
# Smartlead's campaign-level `unsubscribe_text` (top-level settings field, verified live 2026-07):
# when set, Smartlead auto-appends it as the clickable unsubscribe link to EVERY email of EVERY
# sequence step — so the one-line opt-out rides all templates without editing each body, and the
# recipient click fires LEAD_UNSUBSCRIBED → `doNotContact` write-back. A hard compliance floor
# (CAN-SPAM / SG-PDPA): always sent unless an operator overrides the text (never removes it).
DEFAULT_UNSUBSCRIBE_TEXT = "Prefer not to hear from us? Unsubscribe."


def active_sending_account_ids(db: Session, tenant_id) -> list[int]:
    """The tenant's `active` Smartlead sending-inbox ids — the per-tenant DB replacement for the
    secret's global `sl.sending_account_ids()`. Ordered for a stable `add_email_accounts` call;
    coerces to `int` (the RDS Data API can hand BigInteger back as a string)."""
    rows = (
        db.execute(
            select(SendingAccount.smartlead_account_id)
            .where(
                SendingAccount.tenant_id == tenant_id,
                SendingAccount.status == ACTIVE_ACCOUNT,
            )
            .order_by(SendingAccount.smartlead_account_id)
        )
        .scalars()
        .all()
    )
    return [int(x) for x in rows]


_LEAD_PAGE = 100  # GET /campaigns/{id}/leads page size when resolving smartlead_lead_ids
_MAX_LEAD_PAGES = 100  # safety cap (≤ 10k leads) so a bad `total` never loops forever


def _resolve_lead_ids(sl_id, wanted_emails: set[str]) -> dict[str, str]:
    """Resolve `email → smartlead_lead_id` from the campaign's lead roster — the add-leads response
    is counts-only (no ids, verified live). Pages `GET /campaigns/{id}/leads`, stopping once every
    wanted email is found or a short/empty page ends the roster."""
    wanted = {e.lower() for e in wanted_emails}
    got: dict[str, str] = {}
    offset = 0
    for _ in range(_MAX_LEAD_PAGES):
        resp = sl.fetch_campaign_leads(sl_id, offset=offset, limit=_LEAD_PAGE)
        for email, lid in svc.parse_campaign_leads(resp).items():
            if email in wanted:
                got[email] = lid
        rows = resp.get("data") if isinstance(resp, dict) else None
        if len(got) >= len(wanted) or not isinstance(rows, list) or len(rows) < _LEAD_PAGE:
            break
        offset += _LEAD_PAGE
    return got


# --------------------------------------------------------------------------- reaper (no job table)


def _campaign_age_seconds(campaign: Campaign) -> float:
    """Seconds since the campaign was last written — i.e. since it flipped to `launching` (nothing
    else writes the campaign row during a launch). `updated_at` is naive-UTC over the Data API."""
    ts = campaign.updated_at or campaign.created_at
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=UTC)
    return (datetime.now(UTC) - ts).total_seconds()


def reap_if_stale(db: Session, campaign: Campaign) -> bool:
    """Flip a `launching` campaign that outlived any possible worker run to `error`. Idempotent;
    returns True when it reaped (callers then stop treating it as in-flight)."""
    if campaign.status != LAUNCHING or _campaign_age_seconds(campaign) <= MAX_JOB_AGE_SECONDS:
        return False
    db.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id, Campaign.status == LAUNCHING)
        .values(status=ERROR)
    )
    db.commit()
    log.warning("reaped stale launching campaign id=%s", campaign.id)
    campaign.status = ERROR
    return True


# --------------------------------------------------------------------------- enqueue + dispatch


def claim_for_launch(db: Session, campaign: Campaign) -> bool:
    """Atomically flip `campaign` draft/error/sending → launching (and touch updated_at). Returns
    True iff this call won the flip — the guard against two concurrent /launch POSTs double-running.
    """
    won = db.execute(
        update(Campaign)
        .where(Campaign.id == campaign.id, Campaign.status.in_(LAUNCHABLE))
        .values(status=LAUNCHING, updated_at=func.now())
    ).rowcount
    db.commit()
    if won:
        campaign.status = LAUNCHING
    return bool(won)


def dispatch(tenant_id, campaign_id) -> None:
    """Run the worker off the request path: Lambda self async-invoke, else a local daemon thread."""
    payload = {
        JOB_EVENT_KEY: JOB_CAMPAIGN_LAUNCH,
        "tenant_id": str(tenant_id),
        "campaign_id": str(campaign_id),
    }
    fn = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
    if fn:
        import boto3

        boto3.client("lambda").invoke(
            FunctionName=fn, InvocationType="Event", Payload=json.dumps(payload).encode()
        )
    else:
        threading.Thread(
            target=run_launch_job,
            args=(payload["tenant_id"], payload["campaign_id"]),
            daemon=True,
        ).start()


def handle_job_event(event: dict) -> dict:
    """Entry-handler hook for a campaign-launch Lambda event (see app.main.handler)."""
    if event.get(JOB_EVENT_KEY) == JOB_CAMPAIGN_LAUNCH:
        run_launch_job(event["tenant_id"], event["campaign_id"])
    else:
        log.warning("unknown campaign job event: %s", event.get(JOB_EVENT_KEY))
    return {"ok": True}


def _fail(db: Session, campaign_id, message: str) -> None:
    """Guarded terminal write to `error` — only if the worker still owns the launch (launching)."""
    db.execute(
        update(Campaign)
        .where(Campaign.id == campaign_id, Campaign.status == LAUNCHING)
        .values(status=ERROR)
    )
    db.commit()
    log.warning("campaign launch failed id=%s: %s", campaign_id, message[:_ERR_MAX])


# --------------------------------------------------------------------------- worker


def run_launch_job(tenant_id, campaign_id, session_factory=None) -> None:
    """The worker: build the Smartlead campaign + push the approved leads, then flip `sending`.

    Owns its own Session (a thread, or a fresh Lambda invocation). Aborts with NO side effects if
    the campaign was reaped/superseded mid-flight (status no longer `launching`)."""
    tid = uuid.UUID(str(tenant_id))
    cid = uuid.UUID(str(campaign_id))
    if session_factory is None:
        from app.core.db import get_session

        session_factory = get_session
    db = session_factory()
    try:
        campaign = db.get(Campaign, cid)
        # Compare tenant scope as strings: this worker session loads the row fresh from the DB, and
        # the RDS Data API returns UUID columns as `str` (a UUID-object `!=` a str would ALWAYS be
        # true → the campaign would be falsely treated as vanished, and no launch would ever run).
        if campaign is None or str(campaign.tenant_id) != str(tid):
            log.warning("launch: campaign vanished id=%s", campaign_id)
            return
        if campaign.status != LAUNCHING:
            log.warning(
                "launch: campaign %s not launching (reaped/superseded) — abort", campaign_id
            )
            return
        try:
            _do_launch(db, campaign)
        except sl.SmartleadError as e:
            db.rollback()
            _fail(db, cid, f"smartlead error: {e}")
            return
        except Exception:
            log.exception("launch worker crashed id=%s", campaign_id)
            db.rollback()
            _fail(db, cid, "internal error during launch")
            return
        # Success — flip sending, guarded on still owning the launch (not reaped/superseded).
        wrote = db.execute(
            update(Campaign)
            .where(Campaign.id == cid, Campaign.status == LAUNCHING)
            .values(status=SENDING)
        ).rowcount
        db.commit()
        if wrote:
            log.info("campaign %s launched → sending", campaign_id)
        else:
            log.warning("campaign %s finished launch but no longer owned (reaped?)", campaign_id)
    finally:
        db.close()


def _build_schedule(settings: dict) -> dict:
    """The Smartlead schedule body — EF-Q3 daily cap (40) + EF-Q4 prospect-local window, from the
    campaign's stored settings merged over safe defaults."""
    sched = dict(settings.get("schedule") or {})
    sched.setdefault("timezone", settings.get("timezone", "Asia/Singapore"))
    sched.setdefault("days_of_the_week", [1, 2, 3, 4, 5])
    sched.setdefault("start_hour", "09:00")
    sched.setdefault("end_hour", "18:00")
    sched.setdefault("min_time_btw_emails", 10)
    # The cap is EF-Q3 (40); a weak warm-up read lowers it via settings, never raises it silently.
    sched["max_new_leads_per_day"] = int(settings.get("daily_cap", DEFAULT_DAILY_CAP))
    return sched


def _variant_sequences(db: Session, campaign: Campaign) -> list[dict]:
    """Build the Smartlead sequence[] from the campaign's message variants (step 1 = A/B/C variants,
    step 2 = a blank-subject same-thread follow-up)."""
    from app.models import MessageVariant

    variants = (
        db.execute(
            select(MessageVariant)
            .where(MessageVariant.campaign_id == campaign.id)
            .order_by(MessageVariant.key.asc())
        )
        .scalars()
        .all()
    )
    seq_variants = [
        {"subject": v.subject, "email_body": v.body, "variant_label": v.key} for v in variants
    ]
    step1: dict = {"seq_number": 1, "seq_delay_details": {"delay_in_days": 0}}
    if seq_variants:
        step1["subject"] = seq_variants[0]["subject"]
        step1["email_body"] = seq_variants[0]["email_body"]
        step1["seq_variants"] = seq_variants
    # Step 2 — blank subject = same-thread "Re:" bump.
    step2 = {
        "seq_number": 2,
        "seq_delay_details": {"delay_in_days": 2},
        "subject": "",
        "email_body": "Bumping this up, {{first_name}} — worth a short call?",
    }
    return [step1, step2]


def _smartlead_settings(settings: dict) -> dict:
    """The `POST /campaigns/{id}/settings` body — the operator's `smartlead_settings` over a floor
    that GUARANTEES an `unsubscribe_text` (the Smartlead auto-appended opt-out link on every email).
    An operator may customize the wording but a blank/absent value falls back to the default, so no
    launch ships emails without a working unsubscribe link (compliance floor, not a preference)."""
    out = dict(settings.get("smartlead_settings") or {})
    if not (out.get("unsubscribe_text") or "").strip():
        out["unsubscribe_text"] = DEFAULT_UNSUBSCRIBE_TEXT
    return out


def _do_launch(db: Session, campaign: Campaign) -> None:
    """The launch steps — each idempotent so a re-launch resumes exactly the gap."""
    s = get_settings()
    account_ids = active_sending_account_ids(db, campaign.tenant_id)
    if not account_ids:
        raise sl.SmartleadError(
            f"no active sending_account rows for tenant {campaign.tenant_id} "
            "— seed the tenant's warmed Smartlead inbox ids"
        )

    settings = dict(campaign.settings or {})

    # 1. Create the Smartlead campaign once (id stored → a retry never recreates), then push the
    #    one-time setup (sequences, accounts, schedule, settings, webhook), gated on a done flag.
    if not campaign.smartlead_campaign_id:
        created = sl.create_campaign(campaign.name or "HoldSlot campaign")
        sl_id = created.get("id")
        if sl_id is None:
            raise sl.SmartleadError("create_campaign returned no id")
        campaign.smartlead_campaign_id = str(sl_id)
        db.commit()  # persist before any further step, so a crash can resume without recreating

    sl_id = campaign.smartlead_campaign_id
    if not settings.get("sl_setup_done"):
        sl.save_sequences(sl_id, _variant_sequences(db, campaign))
        sl.add_email_accounts(sl_id, account_ids)
        sl.update_schedule(sl_id, _build_schedule(settings))
        sl.update_settings(sl_id, _smartlead_settings(settings))
        token = sl.webhook_path_token()
        if token:
            sl.register_webhook(
                sl_id,
                name="holdslot-ingest",
                webhook_url=f"{s.api_base_url}/webhooks/smartlead/{token}",
                event_types=[
                    "EMAIL_SENT",
                    "EMAIL_OPEN",
                    "EMAIL_LINK_CLICK",
                    "EMAIL_REPLY",
                    "EMAIL_BOUNCE",
                    "LEAD_UNSUBSCRIBED",
                ],
            )
        settings["sl_setup_done"] = True
        campaign.settings = settings
        db.commit()

    # 2. Push the approved + verified-email leads that don't yet have a campaign_lead (resume gap).
    existing = set(
        db.execute(
            select(CampaignLead.prospect_id).where(CampaignLead.campaign_id == campaign.id)
        ).scalars()
    )
    rows = db.execute(
        select(Prospect, ProspectApproval)
        .join(ProspectApproval, ProspectApproval.prospect_id == Prospect.id)
        .where(
            ProspectApproval.batch_id == campaign.batch_id,
            ProspectApproval.decision == "approved",
            Prospect.email_valid.is_(True),
        )
    ).all()
    pending = [(p, a) for p, a in rows if p.id not in existing]

    for group in svc.chunk(pending, svc.MAX_LEADS_PER_ADD):
        by_email: dict[str, tuple] = {}
        lead_list: list[dict] = []
        for prospect, approval in group:
            payload = svc.build_lead_payload(prospect.enrichment or {})
            if payload is None:
                continue
            by_email[payload["email"].lower()] = (prospect, approval)
            lead_list.append(payload)
        if not lead_list:
            continue
        resp = sl.add_leads(sl_id, lead_list)
        # The live add-leads response is counts-only. Honor inline ids if a Smartlead variant
        # returns them, then resolve the rest from the lead roster (GET /campaigns/{id}/leads).
        got = svc.parse_add_leads(resp)
        missing = {e for e in by_email if e not in got}
        if missing:
            got.update(_resolve_lead_ids(sl_id, missing))
        now = datetime.now(UTC)
        # Insert a campaign_lead ONLY for a lead Smartlead accepted (the funnel never shows an
        # unsent lead). A lead missing from the response is left for the next re-launch to retry.
        for (prospect, approval), lead_id in svc.accepted_leads(by_email, got):
            lead = CampaignLead(
                tenant_id=campaign.tenant_id,
                campaign_id=campaign.id,
                prospect_id=prospect.id,
                approval_id=approval.id,
                smartlead_lead_id=lead_id,
                stage=svc.CONTACTED,
                stage_changed_at=now,
            )
            db.add(lead)
            db.flush()  # need lead.id for the ledger row
            db.add(
                OutreachEvent(
                    tenant_id=campaign.tenant_id,
                    campaign_id=campaign.id,
                    campaign_lead_id=lead.id,
                    event_type=svc.STAGE_MOVED,
                    payload={"to": svc.CONTACTED, "via": "launch"},
                    occurred_at=now,
                )
            )
        db.commit()

    # 3. Start sending (idempotent — START on an already-started campaign is a no-op).
    sl.set_status(sl_id, sl.STATUS_START)

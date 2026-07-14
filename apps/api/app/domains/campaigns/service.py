"""Phase E pure core — the funnel state machine + webhook normalization.

Everything money-path and webhook-shaped that can be decided WITHOUT a DB lives here, so the N1 rule
(a non-Aurora unit per money-path branch) is satisfiable off the E0 fixtures alone. The router
(console), `webhooks` (public ingest), and `launch` (async worker) all consume these helpers; none
of the funnel logic is duplicated in a route.

Design invariants (docs/initial-build-plan.md → Phase E):
  * `campaign_lead.stage` is the funnel's single source of truth; Smartlead events are *inputs*.
  * Stage moves go only through `MOVES` (the server allowed-moves map). A manual move that isn't in
    the map is a 409; a webhook-driven move that isn't legal is silently skipped (never a 5xx — a
    5xx triggers Smartlead retry storms).
  * Counts/metrics are DERIVED from the `outreach_event` ledger, never stored.
  * Internal `event_type` keeps OUR lowercase vocabulary; `normalize_event()` absorbs the provider
    name drift (`EMAIL_REPLY`/`LEAD_REPLIED`/`EMAIL_REPLIED`…), and the raw name stays in `payload`.
"""

from __future__ import annotations

import hashlib
from datetime import UTC, datetime

# --------------------------------------------------------------------------- funnel stages + moves

CONTACTED = "contacted"
FOLLOWUP = "followup"
REPLIED = "replied"
MEETING = "meeting"
NOSHOW = "noshow"
BILLABLE = "billable"
DROP = "drop"

# The server allowed-moves map — the mirror of the FE `MOVES` table (CampaignTab.tsx), with ONE
# deliberate addition: `contacted → replied`. A prospect can reply to the FIRST email (still at
# `contacted`, before any follow-up), and triaging that positive must be legal; the FE `MOVES` is
# reconciled to match in E7. Everything else is identical: forward one, back one, plus Drop/DNC.
MOVES: dict[str, list[str]] = {
    CONTACTED: [FOLLOWUP, REPLIED, DROP],
    FOLLOWUP: [CONTACTED, REPLIED, DROP],
    REPLIED: [FOLLOWUP, MEETING, DROP],
    MEETING: [REPLIED, BILLABLE, NOSHOW, DROP],
    NOSHOW: [MEETING, REPLIED, DROP],
    BILLABLE: [MEETING, DROP],
    DROP: [CONTACTED],
}


def is_legal_move(src: str, dst: str) -> bool:
    """True iff `src → dst` is in the allowed-moves map. A no-op (`src == dst`) is NOT a move."""
    return dst in MOVES.get(src, [])


# --------------------------------------------------------------------------- internal event vocab

EMAIL_SENT = "email_sent"
LEAD_OPENED = "lead_opened"
LEAD_CLICKED = "lead_clicked"
LEAD_REPLIED = "lead_replied"
LEAD_BOUNCED = "lead_bounced"
LEAD_UNSUBSCRIBED = "lead_unsubscribed"
# Internal (never from a webhook): the ledger's own workflow rows.
CAMPAIGN_PAUSED = "campaign_paused"
CAMPAIGN_RESUMED = "campaign_resumed"
STAGE_MOVED = "stage_moved"
REPLY_SENT = "reply_sent"

# Provider event-name → our internal vocabulary. Seeded from Smartlead's documented strings PLUS the
# variants that drift across their own docs (R3); the E0 probe's accepted enum confirms/extends it.
# An unmapped name is stored raw (never a 5xx) and never moves a stage — see `normalize_event`.
_NORMALIZE: dict[str, str] = {
    "EMAIL_SENT": EMAIL_SENT,
    "FIRST_EMAIL_SENT": EMAIL_SENT,
    "EMAIL_OPEN": LEAD_OPENED,
    "EMAIL_OPENED": LEAD_OPENED,
    "EMAIL_LINK_CLICK": LEAD_CLICKED,
    "EMAIL_CLICK": LEAD_CLICKED,
    "EMAIL_CLICKED": LEAD_CLICKED,
    "EMAIL_REPLY": LEAD_REPLIED,
    "EMAIL_REPLIED": LEAD_REPLIED,
    "LEAD_REPLIED": LEAD_REPLIED,
    "EMAIL_BOUNCE": LEAD_BOUNCED,
    "EMAIL_BOUNCED": LEAD_BOUNCED,
    "LEAD_BOUNCED": LEAD_BOUNCED,
    "LEAD_UNSUBSCRIBED": LEAD_UNSUBSCRIBED,
    "EMAIL_UNSUBSCRIBED": LEAD_UNSUBSCRIBED,
    "UNSUBSCRIBED": LEAD_UNSUBSCRIBED,
}


def normalize_event(provider_type: str | None) -> str | None:
    """Map a Smartlead provider event-name to our internal `event_type`, case/space-insensitively.
    Returns None for an unknown name → the caller stores it raw and moves no stage (R3/R8)."""
    if not provider_type:
        return None
    return _NORMALIZE.get(str(provider_type).strip().upper())


# Per-lead timeline presentation (the Campaign-tab card log). Direction: `out` = we sent, `in` =
# the prospect acted, `sys` = a workflow row. Only Email is Smartlead-fed at MVP (R6: LinkedIn/
# Calendar/Stripe channels stay empty until F/G), so every live event renders on the Email rail.
_EVENT_DIRECTION: dict[str, str] = {
    EMAIL_SENT: "out",
    REPLY_SENT: "out",
    LEAD_OPENED: "in",
    LEAD_CLICKED: "in",
    LEAD_REPLIED: "in",
    LEAD_BOUNCED: "in",
    LEAD_UNSUBSCRIBED: "in",
    STAGE_MOVED: "sys",
    CAMPAIGN_PAUSED: "sys",
    CAMPAIGN_RESUMED: "sys",
}
_EVENT_TITLE: dict[str, str] = {
    EMAIL_SENT: "Email sent",
    REPLY_SENT: "Reply sent",
    LEAD_OPENED: "Opened",
    LEAD_CLICKED: "Link clicked",
    LEAD_REPLIED: "Prospect replied",
    LEAD_BOUNCED: "Bounced",
    LEAD_UNSUBSCRIBED: "Unsubscribed",
    STAGE_MOVED: "Stage moved",
    CAMPAIGN_PAUSED: "Campaign paused",
    CAMPAIGN_RESUMED: "Campaign resumed",
}


def describe_event(event_type: str, payload: dict | None) -> tuple[str, str, str]:
    """Render one ledger row for the per-lead timeline → `(direction, title, summary)`, all derived
    (never stored). `stage_moved` reads its `from`/`to`/`via` off the payload; a reply/bounce shows
    a short body excerpt; an unknown internal type falls back to a title-cased name. Pure/tested."""
    direction = _EVENT_DIRECTION.get(event_type, "sys")
    title = _EVENT_TITLE.get(event_type, event_type.replace("_", " ").capitalize())
    body = payload or {}
    if event_type == STAGE_MOVED:
        frm, to = body.get("from", ""), body.get("to", "")
        via = body.get("via", "")
        summary = f"{frm} → {to}" + (f" · {via}" if via else "")
    elif event_type == LEAD_REPLIED:
        summary = str(body.get("reply_body") or body.get("preview_text") or "")[:280]
    elif event_type == REPLY_SENT:
        summary = ""
    elif event_type == LEAD_BOUNCED:
        summary = str(body.get("reason") or body.get("bounce_reason") or "")[:200]
    else:
        seq = body.get("sequence_number")
        summary = f"step {seq}" if seq else ""
    return direction, title, summary


# --------------------------------------------------------------------------- webhook payload reads

# Provider timestamp fields, in read priority (a reply carries `time_replied`, a send `time_sent`…).
_TS_FIELDS = (
    "time_replied",
    "time_sent",
    "time_bounced",
    "time_unsubscribed",
    "time_opened",
    "time_clicked",
    "event_timestamp",
    "timestamp",
    "time",
)
# Candidate real provider event-id fields. NOT `webhook_id` (the subscription id, same for every
# event) and NOT `message_id` — the E0 probe (2026-07-11) showed `message_id` is the email's RFC
# Message-ID, shared across that email's events (sent/open/click), so using it would dedupe distinct
# event types into one. Smartlead ships no per-event id → the derived hash (includes `event_type`).
_EVENT_ID_FIELDS = ("sl_event_id", "event_id")
# Candidate lead-email fields — a reply comes FROM the lead, a send goes TO it, so both directions
# plus the explicit lead fields are collected; resolution matches ANY against the campaign's leads.
_EMAIL_FIELDS = ("sl_lead_email", "lead_email", "from_email", "to_email")


def sequence_number(payload: dict) -> int | None:
    """The 1-based sequence step (documented on every sent/open/click/reply event)."""
    raw = payload.get("sequence_number")
    try:
        return int(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


# The per-lead A/B/C variant a Smartlead event reports. At launch we set `variant_label` on each
# step-1 `seq_variant` (== our `MessageVariant.key`); Smartlead echoes the chosen one back on the
# send event. Aliases cover the field-name drift across Smartlead's doc pages (⚠, same posture as
# the email/id resolvers). Read priority: the explicit label fields first.
_VARIANT_FIELDS = (
    "variant_label",
    "email_variant_label",
    "seq_variant_label",
    "sequence_variant_label",
    "email_seq_variant_label",
    "variant",
    "email_variant",
)


def variant_label(payload: dict) -> str | None:
    """The A/B/C variant key a Smartlead event carries for its lead, or None if absent/blank.
    Trimmed to `MessageVariant.key`'s 8-char width so it joins the scoreboard directly (M8)."""
    for f in _VARIANT_FIELDS:
        v = payload.get(f)
        if v is not None and str(v).strip():
            return str(v).strip()[:8]
    return None


def provider_timestamp(payload: dict) -> str:
    """The raw provider timestamp string (for the dedupe hash) — first present of `_TS_FIELDS`."""
    for f in _TS_FIELDS:
        v = payload.get(f)
        if v:
            return str(v)
    return ""


def parse_occurred_at(payload: dict) -> datetime | None:
    """The provider timestamp parsed to a tz-aware UTC datetime (R16 — always UTC-pinned). Returns
    None when absent/unparseable, so the caller can fall back to `now()`."""
    raw = provider_timestamp(payload)
    if not raw:
        return None
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None
    return dt if dt.tzinfo is not None else dt.replace(tzinfo=UTC)


def lead_emails(payload: dict) -> list[str]:
    """Every candidate lead email in the payload, lowercased + de-duped, in read priority. The
    ingest resolves the `campaign_lead` by matching ANY of these against the campaign's known lead
    emails — sidestepping the from/to direction ambiguity across event kinds."""
    seen: list[str] = []
    for f in _EMAIL_FIELDS:
        v = (payload.get(f) or "").strip().lower()
        if v and "@" in v and v not in seen:
            seen.append(v)
    return seen


def _provider_event_id(payload: dict) -> str | None:
    for f in _EVENT_ID_FIELDS:
        v = payload.get(f)
        if v:
            return str(v)
    return None


def dedupe_key(payload: dict, *, campaign_id: str | int | None = None) -> str:
    """The `outreach_event.smartlead_event_id` value — the webhook idempotency key.

    The provider event id if one is present in the real payload (the E0 probe checks), else the
    derived hash `sha256(campaign_id · to_email · event_type · sequence_number · provider_ts)`. A
    Smartlead retry re-sends the identical payload → identical key → the `ON CONFLICT DO NOTHING`
    ingest is a no-op; two genuinely distinct events differ in at least one hashed field."""
    real = _provider_event_id(payload)
    if real:
        return real
    cid = str(campaign_id if campaign_id is not None else payload.get("campaign_id") or "")
    parts = [
        cid,
        str(payload.get("to_email") or ""),
        str(payload.get("event_type") or ""),
        str(payload.get("sequence_number") or ""),
        provider_timestamp(payload),
    ]
    return "sha256:" + hashlib.sha256("|".join(parts).encode()).hexdigest()


def reply_handle(payload: dict) -> dict:
    """The reply-to-thread handle read off an `EMAIL_REPLY` payload (R4 path a). Absent in the
    documented shape → the fields stay None and E5 recovers via `master-inbox/inbox-replies` (R4-b).
    Stored in `outreach_event.payload` so E5 reads it back regardless of source."""
    return {
        "email_stats_id": payload.get("stats_id") or payload.get("email_stats_id"),
        "reply_message_id": payload.get("message_id") or payload.get("reply_message_id"),
        "reply_body": payload.get("reply_body") or payload.get("reply_text"),
        "subject": payload.get("subject"),
        "reply_time": provider_timestamp(payload),
    }


_INBOX_LIST_KEYS = ("data", "inbox_replies", "replies", "results")


def parse_inbox_handle(resp: dict | list, lead_email: str) -> dict:
    """R4-b — recover `{email_stats_id, reply_message_id}` for a lead from a `master-inbox/
    inbox-replies` response (tolerant; the shape is a ⚠). Scans reply rows for one matching the
    lead's email and digs the latest inbound message out of `message_history[]` if needed. `{}` if
    not found — the caller then surfaces "no thread handle yet, retry after sync"."""
    rows: list | None = None
    if isinstance(resp, list):
        rows = resp
    elif isinstance(resp, dict):
        for k in _INBOX_LIST_KEYS:
            v = resp.get(k)
            if isinstance(v, list):
                rows = v
                break
    if not rows:
        return {}
    target = (lead_email or "").strip().lower()
    for row in rows:
        if not isinstance(row, dict):
            continue
        rf = str(row.get("from_email") or row.get("lead_email") or "").strip().lower()
        if target and rf and rf != target:
            continue
        stats = row.get("stats_id") or row.get("email_stats_id")
        msg = row.get("message_id") or row.get("reply_message_id")
        if not (stats or msg):
            hist = row.get("message_history")
            for m in reversed(hist if isinstance(hist, list) else []):
                if isinstance(m, dict) and (
                    m.get("type") in ("REPLY", "reply") or m.get("direction") == "inbound"
                ):
                    stats = stats or m.get("stats_id") or m.get("email_stats_id")
                    msg = msg or m.get("message_id") or m.get("reply_message_id")
                    break
        if stats or msg:
            return {"email_stats_id": stats, "reply_message_id": msg}
    return {}


# --------------------------------------------------------------------------- add-leads response

_LEAD_LIST_KEYS = ("upload_leads", "leads", "lead_ids", "data", "results")
_LEAD_ID_KEYS = ("lead_id", "id", "sl_lead_id")
_LEAD_EMAIL_KEYS = ("email", "lead_email", "to_email")


def parse_add_leads(resp: dict) -> dict[str, str]:
    """`{lower(email): smartlead_lead_id}` from an add-leads response — parsed tolerantly because
    the field-names vary across Smartlead's doc pages (⚠). Finds the per-lead list under any of the
    known container keys and reads each item's id/email under its known aliases. An item with no
    resolvable id is skipped (the launch worker leaves that lead's `smartlead_lead_id` NULL)."""
    rows = None
    for k in _LEAD_LIST_KEYS:
        v = resp.get(k)
        if isinstance(v, list):
            rows = v
            break
    if not rows:
        return {}
    out: dict[str, str] = {}
    for item in rows:
        if not isinstance(item, dict):
            continue
        email = next((str(item[k]).strip().lower() for k in _LEAD_EMAIL_KEYS if item.get(k)), None)
        lead_id = next((str(item[k]) for k in _LEAD_ID_KEYS if item.get(k) is not None), None)
        if email and lead_id:
            out[email] = lead_id
    return out


def parse_campaign_leads(resp: dict) -> dict[str, str]:
    """`{lower(email): smartlead_lead_id}` from a `GET /campaigns/{id}/leads` page. The live roster
    nests the lead under each row's `lead` object (`data:[{lead:{id,email}}]`, verified 2026-07-11);
    this is the launch worker's id resolver since the add-leads response is counts-only. Rows whose
    email/id don't resolve are skipped."""
    rows = resp.get("data")
    if not isinstance(rows, list):
        return {}
    out: dict[str, str] = {}
    for row in rows:
        item = row.get("lead") if isinstance(row, dict) else None
        if not isinstance(item, dict):
            continue
        email = next((str(item[k]).strip().lower() for k in _LEAD_EMAIL_KEYS if item.get(k)), None)
        lead_id = next((str(item[k]) for k in _LEAD_ID_KEYS if item.get(k) is not None), None)
        if email and lead_id:
            out[email] = lead_id
    return out


# --------------------------------------------------------------------------- event → stage effect

# Reply-triage classes (mock vocabulary as strings, never a DB enum — CampaignTab/replies mock).
TRIAGE_POSITIVE = "positive"
TRIAGE_NEGATIVE = "negative"
TRIAGE_OBJECTION = "objection-timing"
TRIAGE_REFERRAL = "referral"
TRIAGE_NUDGE = "nudge"
TRIAGE_CLASSES = [
    TRIAGE_POSITIVE,
    TRIAGE_OBJECTION,
    TRIAGE_REFERRAL,
    TRIAGE_NUDGE,
    TRIAGE_NEGATIVE,
]


def triage_stage(triage_class: str) -> str | None:
    """The stage a triage class advances a lead to: positive → replied, negative → drop, everything
    else (objection-timing / referral / nudge) → no move (the reply is handled, stage unchanged)."""
    if triage_class == TRIAGE_POSITIVE:
        return REPLIED
    if triage_class == TRIAGE_NEGATIVE:
        return DROP
    return None


# --------------------------------------------------------------------------- launch helpers (E3)

MAX_LEADS_PER_ADD = 400  # Smartlead add-leads hard cap per request


def build_lead_payload(enrichment: dict) -> dict | None:
    """The Smartlead lead dict for one enriched prospect, or None if it has no email (never pushed).
    Only the fields Smartlead uses for personalization — no fit/score/internal data leaves."""
    email = (enrichment.get("email") or "").strip()
    if not email or "@" not in email:
        return None
    lead: dict = {"email": email}
    if enrichment.get("first_name"):
        lead["first_name"] = enrichment["first_name"]
    if enrichment.get("last_name"):
        lead["last_name"] = enrichment["last_name"]
    if enrichment.get("company"):
        lead["company_name"] = enrichment["company"]
    return lead


def chunk(items: list, size: int = MAX_LEADS_PER_ADD) -> list[list]:
    """Split `items` into ≤ `size` chunks (the add-leads batch cap; one call at MVP volumes)."""
    size = max(1, size)
    return [items[i : i + size] for i in range(0, len(items), size)]


def accepted_leads(by_email: dict[str, object], got: dict[str, str]) -> list[tuple[object, str]]:
    """The money-path filter: `[(value, smartlead_lead_id)]` for exactly the leads Smartlead
    accepted (present in the add-leads response). A lead missing from the response is NOT inserted —
    the funnel never shows an unsent lead, and the next re-launch retries only the gap."""
    return [(value, got[email]) for email, value in by_email.items() if got.get(email)]


# --------------------------------------------------------------------------- statistics poll (E6)

_STATS_LIST_KEYS = ("data", "statistics", "leads", "results")
_STATS_LEAD_ID_KEYS = ("lead_id", "sl_lead_id", "id")
_STATS_SEQ_KEYS = ("sequence_number", "seq_number", "email_sequence", "last_email_sequence_sent")


def parse_statistics_progress(resp: dict | list) -> dict[str, int]:
    """`{smartlead_lead_id: max sequence step sent}` from a campaign-statistics response — the E6
    drift check (a webhook-missed `followup` shows here). Tolerant: the shape is a ⚠. A row with no
    explicit sequence but a `sent_count`/`email_count` ≥ 2 counts as reaching step 2."""
    rows: list | None = None
    if isinstance(resp, list):
        rows = resp
    elif isinstance(resp, dict):
        for k in _STATS_LIST_KEYS:
            v = resp.get(k)
            if isinstance(v, list):
                rows = v
                break
    if not rows:
        return {}
    out: dict[str, int] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        lead_id = next((str(row[k]) for k in _STATS_LEAD_ID_KEYS if row.get(k) is not None), None)
        if lead_id is None:
            continue
        seq = 0
        for k in _STATS_SEQ_KEYS:
            try:
                seq = max(seq, int(row[k]))
            except (KeyError, TypeError, ValueError):
                continue
        if seq == 0:  # no explicit seq — infer step 2 from a sent-count ≥ 2
            for k in ("sent_count", "email_count", "sent_messages_count"):
                try:
                    if int(row[k]) >= 2:
                        seq = 2
                except (KeyError, TypeError, ValueError):
                    continue
        out[lead_id] = max(out.get(lead_id, 0), seq)
    return out


def event_stage_effect(
    internal_type: str, seq_number: int | None, current_stage: str
) -> str | None:
    """The AUTO stage move a webhook event drives (None = no move; the money path never depends on a
    webhook for `contacted`, which the launch worker sets):

      * `email_sent` seq ≥ 2  → `followup`   (only from `contacted` — never walks a lead backwards)
      * `lead_bounced` / `lead_unsubscribed` → `drop`  (from anywhere but `drop`)
      * `lead_replied` → None (a reply is queued for human triage; it does NOT auto-advance)

    The returned target is only *proposed* — the caller still checks `is_legal_move` and skips it if
    the map forbids it (defensive: a webhook is never a 409)."""
    if internal_type == EMAIL_SENT and (seq_number or 0) >= 2 and current_stage == CONTACTED:
        return FOLLOWUP
    if internal_type in (LEAD_BOUNCED, LEAD_UNSUBSCRIBED) and current_stage != DROP:
        return DROP
    return None

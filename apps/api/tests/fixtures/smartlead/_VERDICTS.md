# E0 live-contract verdicts — Smartlead (captured 2026-07-11)

Driven by `scripts/e_smoke_live.py` against a **scratch campaign (id 3623750)** on the founder's own
inbox (`jason@getholdslot.com`, "Phase E Test Batch"). Every request went through the E2 adapter
(`app/integrations/smartlead/client.py`), so a green call is proof the adapter body matches the live API.

## ⭐ Three launch-blocking contract bugs found + fixed

All three would have broken **every** production launch (the adapter was built from docs; these are the
doc-vs-reality gaps the probe exists to catch).

1. **`add_leads` — top-level `return_lead_ids` is rejected.** Live response:
   `400 {"message":"\"return_lead_ids\" is not allowed"}`. **Fix:** dropped it from the body.

2. **`add_leads` response is COUNTS-ONLY — no per-lead ids.** The real response is
   `{ok, upload_count, total_leads, block_count, duplicate_count, invalid_emails, unsubscribed_leads, …}`
   with **no `upload_leads` / lead-id array**. The launch worker previously read `email→smartlead_lead_id`
   from this response (`parse_add_leads`) → it would have inserted **zero `campaign_lead` rows** while
   Smartlead happily queued the leads (silent broken funnel). **Fix:** resolve ids from the roster
   `GET /campaigns/{id}/leads` → `data[].lead.email` → `data[].lead.id` (new `fetch_campaign_leads` +
   `parse_campaign_leads`; the worker falls back to it whenever the add response lacks an id).
   `lead.id` (e.g. `4155843310`) is the same handle the webhook `lead_id` + `reply_to_thread` use.
   Fixtures: `add_leads_response.json` (real counts-only) · `campaign_leads_response.json` (real roster).

3. **`register_webhook` — `categories` is REQUIRED non-empty.** Live response:
   `400 {"message":"\"categories\" does not contain 1 required value(s)"}`. **Fix:** default to the seven
   standard Smartlead lead categories (`Interested`, `Meeting Request`, `Not Interested`, `Do Not Contact`,
   `Information Request`, `Out Of Office`, `Wrong Person`) so no lead's events are filtered out.

## Two more ingest bugs found from the real `EMAIL_SENT` payload (captured 12:01 UTC)

4. **Webhook lead-id field is `sl_email_lead_id`** (== our stored `smartlead_lead_id`), NOT
   `lead_id`/`sl_lead_id`. `webhooks._resolve_lead` read the wrong keys → it would fall back to the
   slow email match every time. **Fix:** added `sl_email_lead_id` (kept the others as aliases).
5. **`message_id` was in the dedupe `_EVENT_ID_FIELDS`** — but it's the email's RFC Message-ID, shared
   across that email's events (sent/open/click). Using it as `smartlead_event_id` would collide distinct
   event types → an OPEN/CLICK on a sent email would be silently `ON CONFLICT DO NOTHING`-dropped.
   **Fix:** removed it; the derived hash (includes `event_type`) is the key. (`sl_event_id`/`event_id`
   kept — neither appears in the real payload, so the hash is what's used.)

The real `EMAIL_SENT` field map (see `email_sent_seq1.json`): `event_type` · `campaign_id` (int) ·
`sl_email_lead_id`/`sl_email_lead_map_id` · `to_email`/`from_email` · `sequence_number` (int) ·
`time_sent`/`event_timestamp` (ISO +00:00) · `stats_id` · `message_id` · `custom_subject`/`sent_message_body`.

## Verdicts

- **Verdict 1 — accepted event-type enum (R3): CONFIRMED for sent/reply/bounce.** Registration accepts
  all six (`event_type_map` all `true`); the real `event_type` strings are **`EMAIL_SENT`**,
  **`EMAIL_REPLY`**, **`EMAIL_BOUNCE`** (all map via `normalize_event`). `LEAD_UNSUBSCRIBED` confirms
  when its payload arrives. Note: no `EMAIL_OPEN` fired despite an open — Gmail suppresses the pixel.
- **Verdict 2 — R4 reply handle: CONFIRMED.** The real `EMAIL_REPLY` (captured 13:53 UTC) carries **both**
  `stats_id` (`fca6664d-…`) and a top-level `message_id` (the inbound Gmail Message-ID), plus the original
  `sent_message.message_id`. So `reply_to_thread` **path-a works directly**; `master-inbox`/`inbox-replies`
  (R4-b) is a fallback, not the primary. `reply_handle()` reads `stats_id` → `email_stats_id` and the
  reply's `message_id` → `reply_message_id`. Reply field map: `stats_id` · `sl_email_lead_id` (lead) ·
  `sl_lead_email`/`to_email` (lead) · `from_email` (our sender) · `time_replied`/`event_timestamp` (ISO
  +00:00) · `reply_body`/`reply_message.{message_id,html,text}` · `reply_source` · `leadCorrespondence`.
- **Verdict 3 — variant sub-structure: CONFIRMED.** `save_sequences` accepted 2 steps × A/B/C with
  `seq_variants:[{subject, email_body, variant_label}]` on step 1 and a blank-subject same-thread step 2.

## Live methods proven (via the adapter, HTTP 200)

`create_campaign` · `update_schedule` · `update_settings` · `save_sequences` · `add_email_accounts` ·
`add_leads` (post-fix) · `fetch_campaign_leads` · `register_webhook` (post-fix) · `set_status START` ·
`list_email_accounts`. Sending inboxes `20084486`,`20084475` confirmed on the plan.

## EMAIL_BOUNCE captured too (a free, genuine hard bounce) — 2026-07-11

The first send fired from `jason.wong@getholdslot.com` (id 20084486) **to `jason@getholdslot.com`**,
which **does not exist** → Gmail returned "Address not found" → Smartlead POSTed a real
**`EMAIL_BOUNCE`** to the bin. Saved as `email_bounce.json`; validated live through the ingest path:
`normalize_event("EMAIL_BOUNCE") → lead_bounced`, `parse_occurred_at → 2026-07-11T12:01:58+00:00`,
lead-id via `sl_email_lead_id` (same bug-#4 field as EMAIL_SENT). New fields beyond the sent map:
`is_bounced` (true) · `is_sender_originated_bounce` · `bounce_reply_message_id` · `bounce_reply_email`
· `bounce_message.{message_id,html,text,time}`. `move_stage(lead_bounced)` drops the lead (service L482).

**Identity pinned:** sending inboxes are `20084486 = jason.wong@getholdslot.com` and
`20084475 = jason.tse@getholdslot.com`. `jason@getholdslot.com` is a **non-existent** address (bounce).

## Status — ALL 5 webhook payloads REAL; all 3 verdicts CONFIRMED; E0 CLOSED

Real, live-captured + validated: `email_sent_seq1.json` · `email_bounce.json` · `email_reply.json` ·
`lead_unsubscribed.json` (+ API responses `add_leads_response` / `campaign_leads_response` /
`webhook_register_response`). Deliverable round (2026-07-11): bin cleared; scratch `3623750` senders
narrowed to `jason.wong@`; `jason.tse@getholdslot.com` lead (id 4156397120) received seq 1; founder
opened + replied (→ Verdict 2) then master-inbox-unsubscribed (→ the unsub payload).

**`LEAD_UNSUBSCRIBED` field gotchas (both pinned by `test_real_unsub_fixture_ingest_fields`):**
1. **No `sl_email_lead_id`** — the unsub payload carries only `lead_email`/`to_email`, so
   `webhooks._resolve_lead` resolves the lead by EMAIL (its id-then-email fallback), and
   `_unsub_writeback` reads the same for the `doNotContact` append.
2. **`Z`-suffixed timestamp** — `event_timestamp: "…940Z"` (not `+00:00` like the other events);
   `parse_occurred_at` still lands on UTC. `campaign_status` was `COMPLETED` (last active lead gone).

## Unsubscribe link now enforced on every email (2026-07-11)

Beyond ingesting the unsub, the launch path now GUARANTEES a working opt-out link on every sent email:
`launch._smartlead_settings` sets Smartlead's campaign-level **`unsubscribe_text`** (top-level settings
field, verified live: `update_settings` accepted it and `GET` echoed it back) to
`DEFAULT_UNSUBSCRIBE_TEXT` unless an operator overrides the wording — Smartlead auto-appends it as the
clickable unsubscribe link to all sequence steps/variants. The `e_smoke_live.py` probe now sets +
asserts it. Recipient click → `LEAD_UNSUBSCRIBED` → `doNotContact` write-back (the loop this file proves).

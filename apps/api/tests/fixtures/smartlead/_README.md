# Smartlead fixtures — the single Phase-E test-data source

These seven JSON files are the **single test-data source** for every Phase-E unit (E2/E3/E4/E6).
They mirror the request/response + webhook shapes documented in
[`docs/initial-build-plan.md` → Phase E → Smartlead API contract] and `docs/data-schema.md` → Phase E.

## Provenance

**LIVE-captured by the E0 probe (2026-07-11)** on scratch campaign `3623750`. `EMAIL_SENT`,
`EMAIL_BOUNCE`, `EMAIL_REPLY`, and `LEAD_UNSUBSCRIBED` are **real Smartlead webhook payloads** off the
request-bin (see `_VERDICTS.md`); `add_leads_response` / `campaign_leads_response` /
`webhook_register_response` are real API responses. All 5 webhook payloads are now real (unsub captured
via the master-inbox opt-out — the scratch sequence had no in-body link). The probe **overwrote** every
file whose real shape differed from the doc-derived placeholder. Verdicts pinned:

1. **accepted event-type enum** (R3) — real strings are `EMAIL_SENT` / `EMAIL_REPLY` / `EMAIL_BOUNCE`
   / `LEAD_UNSUBSCRIBED` (→ `service.normalize_event()`). **CONFIRMED**.
2. **R4 reply handle** — **CONFIRMED**: the real `EMAIL_REPLY` carries **both** `stats_id` and
   `message_id` → reply-to-thread path-a works directly; `master-inbox` (R4-b) is a fallback.
3. **variant sub-structure** — the `seq_variants` / distribution fields on `save_sequences`. **CONFIRMED**.

The code still **parses tolerantly** (extra/missing fields never crash), so a fixture that drifts
from the live shape degrades a test assertion, never the ingest path.

## Files

| File | Kind | Exercises |
|---|---|---|
| `email_sent_seq1.json` | webhook `EMAIL_SENT` seq 1 | `contacted` (signal only; worker sets the stage) |
| `email_sent_seq2.json` | webhook `EMAIL_SENT` seq 2 | `contacted → followup` auto-move |
| `email_reply.json` | **real** webhook `EMAIL_REPLY` (carries `stats_id`+`message_id`) | reply-queue insert + derived-hash dedupe + path-a reply handle |
| `email_bounce.json` | **real** webhook `EMAIL_BOUNCE` (genuine "address not found") | `→ drop` |
| `lead_unsubscribed.json` | **real** webhook `LEAD_UNSUBSCRIBED` (no lead-id → email resolve; `Z`-ts) | `→ drop` + doNotContact write-back |
| `add_leads_response.json` | `POST /campaigns/{id}/leads` response | tolerant lead-id parse |
| `webhook_register_response.json` | `POST /campaigns/{id}/webhooks` response | register ack |

All identities are the founder's own scratch identity (E0 approval 2026-07-11): **Phase E Test
Batch · getholdslot.com · Jason Tse** — never a prospect row.

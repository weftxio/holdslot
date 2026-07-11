"""E0 live-contract probe — drive the real Smartlead API end-to-end on a scratch campaign.

The E0 gate + the E4 post-deploy live smoke, in one idempotent script (the `c_smoke_live` pattern):
it runs the whole §API-contract table against a **scratch campaign on the founder's own inbox** so
the three ⚠ residues get pinned against reality before E2's adapter tests are trusted, then deletes
the scratch campaign. Everything uses the E2 adapter (`app.integrations.smartlead.client`) — so a
green run is also proof the adapter's request bodies match the live API.

Scratch identity (founder-approved 2026-07-11, internal testing, no prospect rows):
    "Phase E Test Batch" · HoldSlot · getholdslot.com · Jason Tse, Founder

What it captures to tests/fixtures/smartlead/ (overwriting the doc-derived placeholders):
    add_leads_response.json · campaign_leads_response.json · webhook_register_response.json
    (API responses — automatic)
The five WEBHOOK payloads are captured MANUALLY from the request-bin the webhook points at (Smartlead
only POSTs them to a URL) — the script prints exactly what to save where.

The three verdicts to record (into _VERDICTS.md next to the fixtures):
    1. accepted event-type enum   (R3 — which reply/sent/bounce strings the dashboard emits)
    2. R4 reply handle            (does the real EMAIL_REPLY payload carry stats_id / message_id?)
    3. variant sub-structure      (the seq_variants / distribution fields on save_sequences)

Run:  AWS_PROFILE=holdslot python scripts/e_smoke_live.py --capture-url https://<request-bin>
      add --keep to leave the scratch campaign up for the manual reply step (delete later with
      --delete-id <campaign_id>).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "smartlead"

SCRATCH_NAME = "Phase E Test Batch"
# The DELIVERABLE founder inbox — reply/open/unsub captures need a real mailbox (also a Smartlead
# sending inbox: id 20084475). `jason@getholdslot.com` does NOT exist → it bounces "address not
# found", which is exactly how the real EMAIL_BOUNCE fixture was captured (a genuine hard bounce).
# To deliver to jason.tse@ reliably, send from jason.wong@ only (id 20084486) so it isn't a
# send-to-self skip. Never a prospect row.
LEAD_EMAIL_DEFAULT = "jason.tse@getholdslot.com"


def _save_fixture(name: str, payload) -> None:
    path = _FIX / name
    path.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"      captured → tests/fixtures/smartlead/{name}")


def _delete_campaign(sl, campaign_id) -> None:
    """Teardown — not one of the 11 adapter methods (create-only surface), so call the transport
    directly. Try the two documented delete shapes; a failure just leaves the scratch up (harmless)."""
    for method, path in (("DELETE", f"campaigns/{campaign_id}"), ("POST", f"campaigns/{campaign_id}/delete")):
        try:
            sl._request(method, path)
            print(f"[teardown] deleted scratch campaign {campaign_id}")
            return
        except Exception as e:  # noqa: BLE001 — operational script; try the next shape
            last = e
    print(f"[teardown] could not delete {campaign_id} ({last}); delete it by hand in the dashboard")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--capture-url", help="the request-bin URL the webhook POSTs to (E0-approved)")
    ap.add_argument(
        "--account-ids",
        help="comma-separated Smartlead sending-account ids (the pool now lives in the DB per "
        "tenant, not the secret; without this the script falls back to sl.sending_account_ids())",
    )
    ap.add_argument("--lead-email", default=LEAD_EMAIL_DEFAULT, help="founder inbox to add as the 1 lead")
    ap.add_argument("--keep", action="store_true", help="leave the scratch campaign up (manual reply step)")
    ap.add_argument("--delete-id", help="just delete this scratch campaign id and exit")
    args = ap.parse_args()

    from app.integrations.smartlead import client as sl

    if args.delete_id:
        _delete_campaign(sl, args.delete_id)
        return 0
    if not args.capture_url:
        ap.error("--capture-url is required (the E0-approved request-bin)")

    # Preflight — resolve the sending inboxes (CLI override wins; else the legacy secret list).
    accounts = sl.list_email_accounts()
    ids = [int(x) for x in args.account_ids.split(",") if x.strip()] if args.account_ids else sl.sending_account_ids()
    if not ids:
        print("[FAIL] no sending-account ids — pass --account-ids, or seed the tenant's inboxes (E0)")
        return 1
    live = {int(a["id"]) for a in accounts if isinstance(a, dict) and a.get("id") is not None}
    missing = [i for i in ids if i not in live]
    if missing:
        print(f"[FAIL] sending_account_ids {missing} not on the Smartlead plan")
        return 1
    if not sl.webhook_path_token():
        print("[FAIL] secret has no webhook_path_token — mint a 32-byte token_urlsafe (E0)")
        return 1
    print(f"[0/9] preflight OK — {len(ids)} sending inbox(es), webhook token present")

    campaign_id = None
    try:
        camp = sl.create_campaign(SCRATCH_NAME)
        campaign_id = camp.get("id")
        print(f"[1/9] create_campaign → id={campaign_id}")

        sl.update_schedule(
            campaign_id,
            {
                "timezone": "Asia/Singapore",
                "days_of_the_week": [1, 2, 3, 4, 5],
                "start_hour": "09:00",
                "end_hour": "18:00",
                "min_time_btw_emails": 10,
                "max_new_leads_per_day": 40,  # EF-Q3 cap
            },
        )
        print("[2/9] update_schedule → cap 40/inbox, prospect-local window")

        from app.domains.campaigns.launch import DEFAULT_UNSUBSCRIBE_TEXT

        sl.update_settings(
            campaign_id,
            {
                "track_settings": ["DONT_TRACK_EMAIL_OPEN"],
                "stop_lead_settings": "REPLY_TO_AN_EMAIL",
                "unsubscribe_text": DEFAULT_UNSUBSCRIBE_TEXT,  # opt-out link on every email (compliance)
            },
        )
        stored = sl._request("GET", f"campaigns/{campaign_id}").get("unsubscribe_text")
        assert stored == DEFAULT_UNSUBSCRIBE_TEXT, f"unsubscribe_text not stored: {stored!r}"
        print(f"[3/9] update_settings → unsubscribe_text set + verified ({stored!r})")

        # 2 steps × A/B/C — pins the variant sub-structure ⚠ (verdict 3). Blank subject on step 2 =
        # same-thread "Re:". Adjust `email_variants` to whatever the live API accepts, then re-run.
        sequences = [
            {
                "seq_number": 1,
                "seq_delay_details": {"delay_in_days": 0},
                "subject": "A quick idea for {{company_name}}",
                "email_body": "Hi {{first_name}}, one line on why HoldSlot fits {{company_name}}. — Jason",
                "seq_variants": [
                    {"subject": "A quick idea for {{company_name}}", "email_body": "Variant A body", "variant_label": "A"},
                    {"subject": "{{company_name}}: worth 15 min?", "email_body": "Variant B body", "variant_label": "B"},
                    {"subject": "Idea for the {{company_name}} team", "email_body": "Variant C body", "variant_label": "C"},
                ],
            },
            {
                "seq_number": 2,
                "seq_delay_details": {"delay_in_days": 2},
                "subject": "",  # blank = same-thread follow-up
                "email_body": "Bumping this up, {{first_name}} — worth a short call?",
            },
        ]
        seq_resp = sl.save_sequences(campaign_id, sequences)
        print("[4/9] save_sequences → 2 steps × A/B/C (record the accepted variant shape as verdict 3)")

        sl.add_email_accounts(campaign_id, ids)
        print(f"[5/9] add_email_accounts → {ids}")

        add_resp = sl.add_leads(
            campaign_id,
            [{"email": args.lead_email, "first_name": "Jason", "last_name": "Tse", "company_name": "HoldSlot"}],
        )
        _save_fixture("add_leads_response.json", add_resp)
        print(
            f"[6/9] add_leads → 1 lead ({args.lead_email}); counts upload="
            f"{add_resp.get('upload_count')} block={add_resp.get('block_count')} "
            f"dup={add_resp.get('duplicate_count')}"
        )
        # The add response is COUNTS-ONLY — resolve email→lead_id from the roster (the launch path).
        leads_resp = sl.fetch_campaign_leads(campaign_id)
        _save_fixture("campaign_leads_response.json", leads_resp)
        ids = parse_campaign_leads(leads_resp)
        print(f"      resolved lead ids via GET /campaigns/{{id}}/leads: {ids}")

        webhook_url = args.capture_url
        wh_resp = sl.register_webhook(
            campaign_id,
            name="holdslot-e0-probe",
            webhook_url=webhook_url,
            event_types=["EMAIL_SENT", "EMAIL_OPEN", "EMAIL_LINK_CLICK", "EMAIL_REPLY", "EMAIL_BOUNCE", "LEAD_UNSUBSCRIBED"],
        )
        _save_fixture("webhook_register_response.json", wh_resp)
        print(f"[7/9] register_webhook → {webhook_url} (all 6 event types)")

        sl.set_status(campaign_id, sl.STATUS_START)
        print("[8/9] set_status START → campaign sending to the founder inbox")

        print("\n[9/9] MANUAL steps to finish the E0 capture:")
        print(f"      • Watch {webhook_url} for the EMAIL_SENT payload → save as email_sent_seq1.json")
        print(f"      • Reply from {args.lead_email} → save the EMAIL_REPLY payload as email_reply.json")
        print("        …and record whether it carries stats_id/message_id (R4 → verdict 2).")
        print("      • Trigger a bounce (add a known-bad address) + an unsubscribe for the last two fixtures.")
        print("      • Record the exact accepted event_type strings as verdict 1 in _VERDICTS.md.")
        print("\n✅ live contract probe drove all 11 adapter calls without error.")
        return 0
    finally:
        if campaign_id and not args.keep:
            _delete_campaign(sl, campaign_id)
        elif campaign_id:
            print(f"[kept] scratch campaign {campaign_id} left up — delete later: --delete-id {campaign_id}")


def parse_campaign_leads(resp) -> dict:
    from app.domains.campaigns import service as svc

    return svc.parse_campaign_leads(resp)


if __name__ == "__main__":
    sys.exit(main())

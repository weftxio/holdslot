"""F2 live-contract probe — drive the real Google Calendar + Meet REST APIs end-to-end.

The E0 lesson (5 adapter bugs came from a doc-built adapter) applied to Phase F: run every method of
the §Google API contract against the real host seat BEFORE any booking code trusts the adapter, and
commit the captured shapes as the F3/F4 test fixtures. Everything uses the F2 adapter
(`app.integrations.google.client`) — a green run is proof its request bodies match the live API.

The scratch event carries only the founder's own identity (founder attendee, +2 days out) and is
deleted at teardown (delete stays OUT of the 6-method adapter — call the transport directly).

What it captures to tests/fixtures/google/ (overwriting the doc-built placeholders):
    event_insert_response.json   (FP-3; event_insert_pending.json too if a pending create is seen)
    freebusy_response.json       (FP-2)
    conference_records_response.json / participants_response.json  (FP-5/6 — needs --meeting-code
    from the F0 real meeting; skipped with a note if absent)

The three verdicts to record (into _VERDICTS.md next to the fixtures):
    ① is statusCode ever `pending` in practice (GR2)
    ② is the host identifiable in participants[].signedinUser (drives FD-2's duration refinement)
    ③ can one meeting code carry >1 conference record (GR5)

Run:  AWS_PROFILE=holdslot python scripts/f_smoke_live.py --attendee you@example.com \
          [--meeting-code abc-defg-hij]   # the F0 real meeting's code, for FP-5/6
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
from datetime import UTC
from pathlib import Path

_FIX = Path(__file__).resolve().parents[1] / "tests" / "fixtures" / "google"

SCRATCH_SUMMARY = "HoldSlot F2 probe (scratch — safe to ignore)"


def _save_fixture(name: str, payload) -> None:
    (_FIX / name).write_text(json.dumps(payload, indent=2) + "\n")
    print(f"      captured → tests/fixtures/google/{name}")


def _delete_event(g, event_id: str) -> None:
    """Teardown — not one of the 6 adapter methods (read/create only), so call transport directly.
    `sendUpdates=none` so cancelling the scratch doesn't email the founder."""
    try:
        url = (
            f"{g.CALENDAR_BASE}/calendars/primary/events/"
            f"{urllib.parse.quote(event_id)}?sendUpdates=none"
        )
        g._request("DELETE", url)
        print(f"[teardown] deleted scratch event {event_id}")
    except Exception as e:  # noqa: BLE001 — operational script; a failed delete is harmless
        print(f"[teardown] could not delete {event_id} ({e}); delete it by hand in Calendar")


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--attendee", required=True, help="an inbox to invite on the scratch event (yours)"
    )
    ap.add_argument(
        "--meeting-code", help="the F0 real meeting's 10-char code (FP-5/6 records read)"
    )
    ap.add_argument("--keep", action="store_true", help="leave the scratch event up")
    args = ap.parse_args()

    from datetime import datetime, timedelta

    from app.integrations.google import client as g

    # FP-1 — token mint on the real secret.
    tok = g.access_token()
    assert tok and len(tok) > 20, "token mint returned nothing"
    print("[1/6] access_token → minted a delegated Bearer token")

    # FP-2 — freebusy read (next 7 days).
    now = datetime.now(UTC).replace(microsecond=0)
    t_min = now.isoformat().replace("+00:00", "Z")
    t_max = (now + timedelta(days=7)).isoformat().replace("+00:00", "Z")
    busy = g.freebusy(t_min, t_max)
    _save_fixture("freebusy_response.json", {"timeMin": t_min, "timeMax": t_max, "busy": busy})
    print(f"[2/6] freebusy → {len(busy)} busy block(s) on the host seat")

    event_id = None
    try:
        # FP-3 — create a scratch event +2 days (30 min), founder as attendee.
        start = (now + timedelta(days=2)).replace(minute=0, second=0)
        end = start + timedelta(minutes=30)
        start_s = start.isoformat().replace("+00:00", "Z")
        end_s = end.isoformat().replace("+00:00", "Z")
        event = g.create_event(
            summary=SCRATCH_SUMMARY,
            description="HoldSlot F2 live-contract probe — scratch, auto-deleted.",
            start=start_s,
            end=end_s,
            timezone="UTC",
            attendees=[args.attendee],
        )
        event_id = event["id"]
        conf = event.get("conferenceData", {})
        code = conf.get("conferenceId")
        hangout = event.get("hangoutLink", "")
        status = (conf.get("status") or {}).get("statusCode")
        _save_fixture("event_insert_response.json", event)
        assert status in (None, "success"), f"conference create not resolved: {status}"
        assert code and hangout.rstrip("/").endswith(
            code
        ), f"conferenceId {code!r} != hangoutLink tail {hangout!r} (the correlation key)"
        print(f"[3/6] create_event → id={event_id} code={code} (statusCode={status}) ✓ correlation")
        print(f"      ① verdict: statusCode at create = {status!r} (record if ever 'pending')")

        # FP-4 — get_event re-read returns the same ids.
        reread = g.get_event(event_id)
        assert reread["id"] == event_id
        assert (reread.get("conferenceData", {}).get("conferenceId")) == code
        print("[4/6] get_event → same id + conferenceId ✓")

        # FP-5/6 — records + participants read off the F0 REAL meeting (a scratch event nobody joins
        # has no conference record). Skipped with a note if --meeting-code absent.
        if args.meeting_code:
            recs = g.list_conference_records(args.meeting_code)
            _save_fixture("conference_records_response.json", {"conferenceRecords": recs})
            print(f"[5/6] list_conference_records({args.meeting_code}) → {len(recs)} record(s)")
            print(f"      ③ verdict: {len(recs)} record(s) for one code (GR5 = >1 possible?)")
            if recs:
                rec_name = recs[0]["name"]
                parts = g.list_participants(rec_name)
                _save_fixture("participants_response.json", {"participants": parts})
                identifiable = any("signedinUser" in p for p in parts)
                print(f"[6/6] list_participants → {len(parts)} participant(s)")
                print(f"      ② verdict: host identifiable via signedinUser = {identifiable}")
            else:
                print("[6/6] no record yet for that code — re-run after the meeting is held")
        else:
            print("[5/6] --meeting-code not given → skipped records/participants (FP-5/6)")
            print(
                "[6/6] run again with the F0 meeting's code to capture the held-evidence fixtures"
            )

        print("\n✅ live contract probe drove all reachable Google methods without error.")
        print("   Record ①②③ in tests/fixtures/google/_VERDICTS.md, then trust the F2 adapter.")
        return 0
    finally:
        if event_id and not args.keep:
            _delete_event(g, event_id)
        elif event_id:
            print(f"[kept] scratch event {event_id} left up — delete it by hand later")


if __name__ == "__main__":
    sys.exit(main())

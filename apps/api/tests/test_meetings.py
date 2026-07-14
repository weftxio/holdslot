"""Phase F pure-core units — booking slots + the qualify/billing rule (no DB, no network).

Every money-path branch has a non-Aurora unit here (the N1 rule), most off the F2 Google fixtures.
The DB-gated booking/sweep/read integration lives in `test_meetings_db.py` (skips w/o Aurora).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from app.domains.meetings import service as m

_FIX = Path(__file__).resolve().parent / "fixtures" / "google"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text())


def _dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


# ============================================================ F3 — booking slots + link state


HK_AVAIL = {
    "availability": {
        "tz": "Asia/Hong_Kong",
        "meeting_minutes": 30,
        "windows": {d: [["10:00", "11:00"]] for d in ("mon", "tue", "wed", "thu", "fri")},
    }
}
# A Monday 00:00 UTC (= 08:00 Mon HKT). min-notice (24h) pushes the first offerable day to Tuesday.
NOW = _dt("2026-07-13T00:00:00Z")


def test_slots_windows_minus_notice_utc_weekdays():
    """FT3-8 — windows ∖ busy · ≥24h notice · 5 weekdays · UTC instants · HK-TZ conversion
    (R16/N18)."""
    slots = m.available_slots(HK_AVAIL, busy=[], now=NOW)
    # 10:00 HKT == 02:00 UTC; two 30-min slots/day (10:00, 10:30).
    assert "2026-07-14T02:00:00Z" in slots  # Tuesday, the first day ≥24h out
    assert "2026-07-14T02:30:00Z" in slots
    # Monday's own slots (02:00Z Mon) are inside the 24h window → never offered.
    assert "2026-07-13T02:00:00Z" not in slots
    # every slot is ≥ now+24h, ends with Z, and lands on a weekday.
    min_start = NOW + timedelta(hours=24)
    for s in slots:
        assert s.endswith("Z")
        assert _dt(s) >= min_start
        assert _dt(s).astimezone(m._zone("Asia/Hong_Kong")).weekday() < 5
    # exactly 5 weekdays offered (Tue–Fri + next Mon), 2 slots each = 10.
    assert len(slots) == 10


def test_availability_of_defaults_when_absent():
    """No `availability` → the FD-1 default (Mon–Fri 10:00–18:00, host TZ, 30-min)."""
    tz, minutes, windows = m.availability_of(None)
    assert (tz, minutes) == (m.DEFAULT_TZ, m.DEFAULT_MEETING_MINUTES)
    assert windows == m.DEFAULT_WINDOWS
    assert m.availability_of({"availability": {}})[2] == m.DEFAULT_WINDOWS


def test_availability_of_tolerates_malformed_fields():
    """M11 — a bad Brief edit must degrade to the default, never raise (this runs on every
    meetings-surface read + the public booking page)."""
    # non-dict availability → all defaults
    tz, minutes, windows = m.availability_of({"availability": "nope"})
    assert (tz, minutes, windows) == (m.DEFAULT_TZ, m.DEFAULT_MEETING_MINUTES, m.DEFAULT_WINDOWS)
    # meeting_minutes garbage / non-positive → default minutes
    assert m.availability_of({"availability": {"meeting_minutes": "abc"}})[1] == (
        m.DEFAULT_MEETING_MINUTES
    )
    assert m.availability_of({"availability": {"meeting_minutes": 0}})[1] == (
        m.DEFAULT_MEETING_MINUTES
    )
    # non-string tz → default tz
    assert m.availability_of({"availability": {"tz": 123}})[0] == m.DEFAULT_TZ


def test_clean_windows_drops_bad_and_keeps_good():
    """M11 — a one-element window, a non-HH:MM value, a reversed window, and a non-list day are all
    dropped; a valid day survives. A fully-unusable value falls back to the default."""
    av = {
        "availability": {
            "windows": {
                "mon": [["10:00", "12:00"], ["bad"], ["18:00", "09:00"], ["9", "x"]],
                "tue": "not-a-list",
                "zzz": [["10:00", "11:00"]],  # not a weekday key
            }
        }
    }
    windows = m.availability_of(av)[2]
    assert windows == {"mon": [["10:00", "12:00"]]}  # only the one valid window survives
    # a windows dict with nothing usable → the Mon–Fri default
    assert m.availability_of({"availability": {"windows": {"mon": [["bad"]]}}})[2] == (
        m.DEFAULT_WINDOWS
    )


def test_available_slots_never_raises_on_malformed_brief():
    """M11 — the slot builder + grid check stay 500-proof on a malformed Brief (they'd IndexError /
    ValueError before the fix)."""
    bad = {"availability": {"meeting_minutes": "oops", "windows": {"mon": [["9"]]}}}
    slots = m.available_slots(bad, busy=[], now=NOW)  # falls back to the default grid
    assert isinstance(slots, list) and slots
    assert m.is_grid_slot(bad, slots[0], NOW) is True


def test_slots_exclude_busy_blocks():
    busy = [{"start": "2026-07-14T02:00:00Z", "end": "2026-07-14T02:30:00Z"}]
    slots = m.available_slots(HK_AVAIL, busy=busy, now=NOW)
    assert "2026-07-14T02:00:00Z" not in slots  # masked by the busy block (FT3-8 / FA-2)
    assert "2026-07-14T02:30:00Z" in slots  # the adjacent slot survives


def test_default_availability_when_absent():
    """FD-1 — no availability doc → Mon–Fri 10:00–18:00 default, so slots still exist."""
    slots = m.available_slots({}, busy=[], now=NOW)
    assert slots and all(s.endswith("Z") for s in slots)


def test_is_grid_slot_rejects_tampered():
    """FT3-15 — a slot off the availability grid / outside notice is never offerable."""
    assert m.is_grid_slot(HK_AVAIL, "2026-07-14T02:00:00Z", NOW)  # a real offered slot
    assert not m.is_grid_slot(HK_AVAIL, "2026-07-14T05:00:00Z", NOW)  # outside the window
    assert not m.is_grid_slot(HK_AVAIL, "2026-07-13T02:00:00Z", NOW)  # inside the 24h notice
    assert not m.is_grid_slot(HK_AVAIL, "not-a-date", NOW)  # garbage


def test_slot_is_free_rechecks_busy():
    """FT3-12 — the re-check catches a slot that just became busy."""
    busy = [{"start": "2026-07-14T02:00:00Z", "end": "2026-07-14T02:30:00Z"}]
    assert not m.slot_is_free("2026-07-14T02:00:00Z", 30, busy)
    assert m.slot_is_free("2026-07-14T02:30:00Z", 30, busy)


def test_inject_booking_link_placeholder_or_append():
    """FT3-1 — substitute the placeholder, else append."""
    assert m.inject_booking_link("Pick a time: {{booking_link}} — thanks", "URL") == (
        "Pick a time: URL — thanks"
    )
    assert m.inject_booking_link("Grab a slot:", "URL") == "Grab a slot:\n\nURL"


def test_link_state_machine():
    """FT3-5/6/7 — valid · used · expired computed on read."""
    future = NOW + timedelta(days=3)
    past = NOW - timedelta(days=1)
    assert m.link_state(None, future, NOW) == "valid"
    assert m.link_state(NOW, future, NOW) == "used"  # used_at set wins
    assert m.link_state(None, past, NOW) == "expired"
    assert m.link_state(None, None, NOW) == "expired"


# ============================================================ F4 — qualify / billing (money)


def test_meeting_code_extraction():
    assert m.meeting_code("https://meet.google.com/abc-defg-hij") == "abc-defg-hij"
    assert m.meeting_code("https://meet.google.com/abc-defg-hij/") == "abc-defg-hij"
    assert m.meeting_code(None) is None


def test_held_requires_record_and_two_participants():
    """FD-2 — an ended record + ≥2 participants = held; host-alone is NOT held."""
    rec = _load("conference_records_response.json")["conferenceRecords"][0]
    two = _load("participants_response.json")["participants"]
    alone = _load("participants_host_alone.json")["participants"]
    assert m.is_held(rec, two) is True
    assert m.is_held(rec, alone) is False  # host waiting alone must never bill
    assert m.is_held(None, two) is False  # no record


def test_ongoing_record_not_ended():
    """FT4-2 — an ongoing record (endTime unset) is skipped by the sweep."""
    rec = _load("conference_records_ongoing.json")["conferenceRecords"][0]
    assert m.record_ended(rec) is False


def test_duration_ceil_minutes():
    """FT4-15 — ceil((end−start)/60) across a boundary."""
    rec = _load("conference_records_response.json")["conferenceRecords"][0]
    assert m.record_duration_min(rec) == 47  # 10:00:00 → 10:47:00
    over = {"startTime": "2026-07-15T10:00:00Z", "endTime": "2026-07-15T11:00:30Z"}
    assert m.record_duration_min(over) == 61  # 60m30s → ceil 61


def test_outcome_qualified_boundary():
    """FT4-3/4/5 — ≥10 min qualifies (inclusive), <10 is a short call, not-held is a no-show."""
    assert m.outcome_for(held=True, duration_min=47) == "qualified"
    assert m.outcome_for(held=True, duration_min=10) == "qualified"  # boundary is inclusive
    assert m.outcome_for(held=True, duration_min=9) == "short_call"
    assert m.outcome_for(held=False, duration_min=0) == "noshow"


def test_select_record_picks_longest_in_window():
    """FT4-12 / GR5 — deterministic pick = longest ended record overlapping the meeting window."""
    sched = _dt("2026-07-15T10:00:00Z")
    recs = [
        {"name": "r1", "startTime": "2026-07-15T10:00:00Z", "endTime": "2026-07-15T10:05:00Z"},
        {"name": "r2", "startTime": "2026-07-15T10:10:00Z", "endTime": "2026-07-15T10:52:00Z"},
        {"name": "r3", "startTime": "2026-07-15T10:00:00Z", "endTime": None},  # ongoing → ignored
    ]
    assert m.select_record(recs, sched)["name"] == "r2"  # 42 min beats 5 min
    assert m.select_record([], sched) is None


def test_is_billable_and_chip_matrix():
    """FT4-11 — the derived billable matrix + the ledger chip."""
    now = NOW
    win_past = now - timedelta(hours=1)
    win_future = now + timedelta(hours=1)
    # qualified + amount + window passed + undisputed → billable, chip Billed.
    assert m.is_billable("qualified", 500, win_past, False, now) is True
    assert m.billing_chip("qualified", 500, win_past, False, now) == "Billed"
    # in-window → not yet billable, chip Held.
    assert m.is_billable("qualified", 500, win_future, False, now) is False
    assert m.billing_chip("qualified", 500, win_future, False, now) == "Held"
    # disputed → never billable, Not billable.
    assert m.is_billable("qualified", 500, win_past, True, now) is False
    assert m.billing_chip("qualified", 500, win_past, True, now) == "Not billable"
    # no amount (no approval evidence) → never billable.
    assert m.is_billable("qualified", None, win_past, False, now) is False
    # short_call / noshow → never billable.
    assert m.is_billable("short_call", None, None, False, now) is False
    assert m.billing_chip("noshow", None, None, False, now) == "Not billable"


def test_dispute_window_end_is_48h():
    end = _dt("2026-07-15T10:47:00Z")
    assert m.dispute_window_end(end) == end + timedelta(hours=48)


# ============================================================ F5 — read derivations


def test_booking_status_triple():
    """FT5-3 — Confirmed (meeting exists) · Awaiting (valid link) · Expired (past-TTL link)."""
    assert m.booking_status(has_meeting=True, state="used") == "Confirmed"
    assert m.booking_status(has_meeting=False, state="valid") == "Awaiting confirm"
    assert m.booking_status(has_meeting=False, state="expired") == "Expired"


def test_feedback_overdue_flips_at_5_days():
    """FT5-5 — overdue exactly past 5 days pending."""
    ref = NOW - timedelta(days=5, minutes=1)
    assert m.feedback_overdue(ref, None, NOW) is True
    assert m.feedback_overdue(NOW - timedelta(days=4), None, NOW) is False
    assert m.feedback_overdue(ref, NOW, NOW) is False  # answered → never overdue


def test_feedback_state():
    assert m.feedback_state(False, NOW) == "Received"
    assert m.feedback_state(True, None) == "Pending"
    assert m.feedback_state(False, None) == "None"


def test_per_meeting_price_constant():
    assert m.PER_MEETING_USD == 500


# ============================================================ M2 — free/busy outage sentinel


def test_read_busy_returns_none_sentinel_on_google_error(monkeypatch):
    """M2 — a free/busy read that hits a GoogleError returns the `None` sentinel, NOT `[]`. `[]`
    means 'no busy intervals' (every slot free), so the old behaviour offered the full grid + let
    the POST re-check pass during an outage → a double-booked seat. `None` lets `view_booking` show
    no slots and `book_meeting` 503+release instead."""
    import app.integrations.google.client as g
    from app.domains.meetings import public

    def _boom(*a, **k):
        raise g.GoogleError("calendar outage")

    monkeypatch.setattr(g, "freebusy", _boom)
    assert public._read_busy(NOW) is None

    # a healthy read still passes the busy intervals straight through (unchanged path).
    monkeypatch.setattr(g, "freebusy", lambda *a, **k: [{"start": "s", "end": "e"}])
    assert public._read_busy(NOW) == [{"start": "s", "end": "e"}]


# ============================================================ M16 — public feedback input caps


def test_feedback_in_caps_bound_public_input():
    """M16 — the public token-authed FeedbackIn must bound its free fields so a link holder can't
    store MBs on the meeting row. Normal input passes; oversize is rejected."""
    import pytest
    from pydantic import ValidationError

    from app.domains.meetings.schemas import FeedbackIn

    ok = FeedbackIn(rating=5, chips=["Relevant to me", "Good timing"], comment="Useful, thanks.")
    assert ok.rating == 5 and len(ok.chips) == 2

    with pytest.raises(ValidationError):
        FeedbackIn(rating=5, comment="x" * 2001)  # comment cap
    with pytest.raises(ValidationError):
        FeedbackIn(rating=5, chips=["ok", "y" * 65])  # per-chip cap
    with pytest.raises(ValidationError):
        FeedbackIn(rating=5, chips=[f"c{i}" for i in range(13)])  # chip-count cap

"""Phase F meeting logic — pure functions, no DB, no network (the `campaigns/service` posture).

Everything money-adjacent lives here so it can be unit-tested off the F2 Google fixtures with no
Aurora (the N1 rule). Three groups:
  * booking (F3): availability windows → bookable slots (windows ∩ free/busy, ≥24h notice, UTC
    instants), the never-404 link state machine, the reply booking-link injection;
  * qualify (F4): meeting-code correlation, the held/duration/outcome derivation off Meet conference
    records + participants, and the derived `amount`/dispute-window/`is_billable` billing rule;
  * reads (F5): the bookings status triple + feedback-overdue derivations.

The one money constant lives here (the `DEFAULT_DAILY_CAP` precedent) — NOT in `config.Settings`.
"""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from app.core.security import as_utc

# The computed per-qualified-meeting price (a computed amount, not a charge until Stripe at G). The
# FE mirrors it in lib/workspace/constants.ts as the display const.
PER_MEETING_USD = 500

# A held meeting qualifies (bills) only once it runs at least this long (backend-development-plan
# §7).
QUALIFY_MIN_MINUTES = 10
# The client dispute window: billing flips Held → Billed only this long after the meeting ends.
DISPUTE_WINDOW_HOURS = 48
# A no-show is decided only this long past the scheduled start with no conference record (FD-3).
NOSHOW_GRACE_HOURS = 24
# Feedback that has sat unanswered longer than this reads "overdue" (the needs-attention nudge).
FEEDBACK_OVERDUE_DAYS = 5

# Booking slot geometry (FD-5).
MIN_NOTICE_HOURS = 24
SLOT_WEEKDAYS = 5  # offer the next 5 configured weekdays

# Availability default (FD-1) when `brief.data.availability` is absent — Mon–Fri 10:00–18:00 host
# TZ.
_WEEKDAY_KEYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")  # date.weekday(): 0=mon
DEFAULT_TZ = (
    "Asia/Singapore"  # host TZ default (UTC+8); the founder overrides it in the Brief at F0
)
DEFAULT_MEETING_MINUTES = 30
DEFAULT_WINDOWS: dict[str, list[list[str]]] = {d: [["10:00", "18:00"]] for d in _WEEKDAY_KEYS[:5]}


# ------------------------------------------------------------------------------- time helpers


def parse_iso(s: str) -> datetime:
    """Parse an RFC3339 / ISO instant (Z or +00:00) to an aware UTC datetime (the R16/N18 pin)."""
    return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(UTC)


def iso_z(dt: datetime) -> str:
    """Serialize an instant as a UTC `…Z` string (the FE renders viewer-local from this)."""
    return as_utc(dt).isoformat().replace("+00:00", "Z")


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError, TypeError):
        return ZoneInfo("UTC")


def _hm(s: str) -> time:
    h, m = s.split(":")
    return time(int(h), int(m))


# ------------------------------------------------------------------------------- F3: booking slots


def availability_of(brief_data: dict | None) -> tuple[str, int, dict]:
    """(tz, meeting_minutes, windows) from `brief.data.availability`, falling back to the FD-1
    default (Mon–Fri 10:00–18:00 host TZ) for any missing OR MALFORMED piece.

    The Brief is founder-authored free JSON, and this runs on every meetings-surface read + the
    public booking page — so a bad edit (`meeting_minutes: "abc"`, a one-element window, a non-dict
    `availability`) must degrade to the default, never 500 the whole surface (M11)."""
    av = (brief_data or {}).get("availability")
    if not isinstance(av, dict):
        av = {}
    tz = av.get("tz")
    tz = tz if isinstance(tz, str) and tz.strip() else DEFAULT_TZ
    try:
        minutes = int(av.get("meeting_minutes") or DEFAULT_MEETING_MINUTES)
    except (TypeError, ValueError):
        minutes = DEFAULT_MEETING_MINUTES
    if minutes <= 0:
        minutes = DEFAULT_MEETING_MINUTES
    return tz, minutes, _clean_windows(av.get("windows"))


def _clean_windows(raw) -> dict[str, list[list[str]]]:
    """Validate `availability.windows` into `{weekday: [[HH:MM, HH:MM], ...]}`, dropping any
    malformed day/window (FD-1, M11). A fully-unusable value falls back to the Mon–Fri default so
    one bad Brief edit can't crash the slot builder (`_hm` unpack / `time()` ValueError)."""
    if not isinstance(raw, dict):
        return DEFAULT_WINDOWS
    cleaned: dict[str, list[list[str]]] = {}
    for day, wins in raw.items():
        if day not in _WEEKDAY_KEYS or not isinstance(wins, list):
            continue
        good: list[list[str]] = []
        for win in wins:
            if not isinstance(win, (list, tuple)) or len(win) < 2:
                continue
            start_s, end_s = str(win[0]), str(win[1])
            try:
                if _hm(start_s) < _hm(end_s):
                    good.append([start_s, end_s])
            except (ValueError, TypeError):
                continue
        if good:
            cleaned[day] = good
    return cleaned or DEFAULT_WINDOWS


def _overlaps(s: datetime, e: datetime, busy: list[tuple[datetime, datetime]]) -> bool:
    return any(s < be and bs < e for bs, be in busy)


def available_slots(
    brief_data: dict | None, busy: list[dict], now: datetime, *, ignore_busy: bool = False
) -> list[str]:
    """Bookable slot instants (UTC `…Z` ISO): the availability windows cut into `meeting_minutes`
    steps over the next `SLOT_WEEKDAYS` configured weekdays, ≥`MIN_NOTICE_HOURS` out, minus the
    host's free/busy `busy` intervals. `ignore_busy=True` returns the raw grid (the POST tamper
    check — a slot off this grid was never offered)."""
    tz_name, minutes, windows = availability_of(brief_data)
    tz = _zone(tz_name)
    now = as_utc(now)
    min_start = now + timedelta(hours=MIN_NOTICE_HOURS)
    busy_iv: list[tuple[datetime, datetime]] = []
    if not ignore_busy:
        busy_iv = [
            (parse_iso(b["start"]), parse_iso(b["end"]))
            for b in (busy or [])
            if b.get("start") and b.get("end")
        ]
    out: list[str] = []
    # Start the scan at the first day that can carry a ≥24h-notice slot, so "next 5 weekdays" counts
    # from ≥24h out (today, if inside the notice window, never counts).
    day = min_start.astimezone(tz).date()
    weekdays_used, scanned = 0, 0
    while weekdays_used < SLOT_WEEKDAYS and scanned < 21:  # cap the forward scan at 3 weeks
        day_windows = windows.get(_WEEKDAY_KEYS[day.weekday()]) or []
        if day_windows:
            weekdays_used += 1
            for win in day_windows:
                out.extend(_slots_in_window(day, win, minutes, tz, min_start, busy_iv))
        day += timedelta(days=1)
        scanned += 1
    return out


def _slots_in_window(
    day: date,
    win: list[str],
    minutes: int,
    tz: ZoneInfo,
    min_start: datetime,
    busy: list[tuple[datetime, datetime]],
) -> list[str]:
    start_t, end_t = _hm(win[0]), _hm(win[1])
    cur = datetime.combine(day, start_t, tzinfo=tz)
    win_end = datetime.combine(day, end_t, tzinfo=tz)
    step = timedelta(minutes=minutes)
    out: list[str] = []
    while cur + step <= win_end:
        s_utc = cur.astimezone(UTC)
        e_utc = s_utc + step
        if s_utc >= min_start and not _overlaps(s_utc, e_utc, busy):
            out.append(iso_z(s_utc))
        cur += step
    return out


def is_grid_slot(brief_data: dict | None, slot_iso: str, now: datetime) -> bool:
    """True iff `slot_iso` is on the availability grid (≥24h notice) IGNORING busy — a slot that
    fails this was never offerable, i.e. tampered/outside windows (FT3-15 → 400)."""
    try:
        slot = iso_z(parse_iso(slot_iso))
    except (ValueError, TypeError):
        return False
    return slot in set(available_slots(brief_data, [], now, ignore_busy=True))


def slot_is_free(slot_iso: str, minutes: int, busy: list[dict]) -> bool:
    """The re-check at POST — the offered slot must still be clear of a freshly-read busy set."""
    s = parse_iso(slot_iso)
    e = s + timedelta(minutes=minutes)
    busy_iv = [
        (parse_iso(b["start"]), parse_iso(b["end"]))
        for b in (busy or [])
        if b.get("start") and b.get("end")
    ]
    return not _overlaps(s, e, busy_iv)


def inject_booking_link(text: str, url: str) -> str:
    """Substitute a `{{booking_link}}` placeholder in the reply, or append it if none present."""
    if "{{booking_link}}" in text:
        return text.replace("{{booking_link}}", url)
    return f"{text.rstrip()}\n\n{url}"


# ------------------------------------------------------------------------------- link state machine


def link_state(used_at: datetime | None, expires_at: datetime | None, now: datetime) -> str:
    """valid · used · expired — the never-404 token state (booking + feedback links share it)."""
    if used_at is not None:
        return "used"
    if expires_at is None or as_utc(expires_at) < as_utc(now):
        return "expired"
    return "valid"


# ------------------------------------------------------------------------------- F4: qualify


def meeting_code(meet_link: str | None) -> str | None:
    """The 10-char Meet code = the last path segment of the join URL (== conferenceData.conferenceId
    == the Meet REST `space.meeting_code`). The one correlation key."""
    if not meet_link:
        return None
    tail = meet_link.rstrip("/").rsplit("/", 1)[-1]
    return tail or None


def record_ended(record: dict) -> bool:
    """A conference record with `endTime` set has finished; unset = ongoing (the sweep skips it)."""
    return bool(record.get("endTime"))


def select_record(records: list[dict], scheduled_at: datetime) -> dict | None:
    """GR5 — pick one ended record deterministically: the longest-duration record overlapping
    `[scheduled_at − 60min, scheduled_at + 24h]` (a rejoin-after-empty can yield several)."""
    ended = [r for r in records if record_ended(r)]
    if not ended:
        return None
    lo = as_utc(scheduled_at) - timedelta(minutes=60)
    hi = as_utc(scheduled_at) + timedelta(hours=24)
    windowed = [
        r for r in ended if parse_iso(r["startTime"]) < hi and lo < parse_iso(r["endTime"])
    ] or ended
    return max(windowed, key=lambda r: parse_iso(r["endTime"]) - parse_iso(r["startTime"]))


def record_duration_min(record: dict) -> int:
    """ceil((endTime − startTime) / 60) — the FD-2 base measure (whole minutes, rounding up)."""
    span = parse_iso(record["endTime"]) - parse_iso(record["startTime"])
    return math.ceil(span.total_seconds() / 60)


def is_held(record: dict | None, participants: list[dict]) -> bool:
    """FD-2 — held iff an ENDED conference record exists AND ≥2 participants joined (a host waiting
    alone must never bill)."""
    return bool(record and record_ended(record)) and len(participants) >= 2


def outcome_for(*, held: bool, duration_min: int) -> str:
    """held ≥10 min → qualified · held <10 → short_call. (No record → the caller sets `noshow`.)"""
    if not held:
        return "noshow"
    return "qualified" if duration_min >= QUALIFY_MIN_MINUTES else "short_call"


def dispute_window_end(record_end: datetime) -> datetime:
    return as_utc(record_end) + timedelta(hours=DISPUTE_WINDOW_HOURS)


def is_billable(
    outcome: str | None,
    amount,
    dispute_window_ends_at: datetime | None,
    disputed: bool,
    now: datetime,
) -> bool:
    """`billable` is NEVER stored — derived: qualified AND amount stamped AND the 48h window has
    passed AND not disputed. No `amount` (no `approval_id` evidence) → never billable."""
    return (
        outcome == "qualified"
        and amount is not None
        and dispute_window_ends_at is not None
        and as_utc(dispute_window_ends_at) < as_utc(now)
        and not disputed
    )


def billing_chip(
    outcome: str | None,
    amount,
    dispute_window_ends_at: datetime | None,
    disputed: bool,
    now: datetime,
) -> str:
    """The ledger chip: Held (in-window) · Billed (window passed) · Not billable
    (short_call / noshow / disputed / no amount)."""
    if outcome == "qualified" and amount is not None and not disputed:
        past = dispute_window_ends_at is not None and as_utc(dispute_window_ends_at) < as_utc(now)
        return "Billed" if past else "Held"
    return "Not billable"


# ------------------------------------------------------------------------------- F5: read
# derivations


def booking_status(*, has_meeting: bool, state: str) -> str:
    """The client-status Booking chip: Confirmed (a meeting exists) · Awaiting confirm (live unused
    link) · Expired (past-TTL unused link)."""
    if has_meeting:
        return "Confirmed"
    return "Awaiting confirm" if state == "valid" else "Expired"


def feedback_overdue(
    reference: datetime | None, feedback_at: datetime | None, now: datetime
) -> bool:
    """Overdue = a held meeting still awaiting feedback more than FEEDBACK_OVERDUE_DAYS after its
    reference instant (the ingest/scheduled time)."""
    if feedback_at is not None or reference is None:
        return False
    return as_utc(now) - as_utc(reference) > timedelta(days=FEEDBACK_OVERDUE_DAYS)


def feedback_state(has_live_link: bool, feedback_at: datetime | None) -> str:
    """Received (answered) · Pending (a live link out) · None (nothing sent yet)."""
    if feedback_at is not None:
        return "Received"
    return "Pending" if has_live_link else "None"

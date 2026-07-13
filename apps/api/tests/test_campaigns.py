"""Phase E pure-core units — the funnel state machine + webhook normalization (no DB, no network).

Every money-path branch has a non-Aurora unit here (the N1 rule), all off the E0 Smartlead fixtures.
The DB-gated launch/webhook/queue integration lives in `test_campaigns_db.py` (skips w/o Aurora).
"""

from __future__ import annotations

import json
from pathlib import Path

from app.domains.campaigns import service as svc

_FIX = Path(__file__).resolve().parent / "fixtures" / "smartlead"


def _load(name: str) -> dict:
    return json.loads((_FIX / name).read_text())


# --------------------------------------------------------------------------- allowed-moves map


def test_moves_map_mirrors_fe_plus_contacted_replied():
    # forward one / back one / drop, plus the deliberate contacted→replied (first-email reply).
    assert svc.is_legal_move(svc.CONTACTED, svc.FOLLOWUP)
    assert svc.is_legal_move(svc.CONTACTED, svc.REPLIED)  # the E-added rung
    assert svc.is_legal_move(svc.CONTACTED, svc.DROP)
    assert svc.is_legal_move(svc.FOLLOWUP, svc.REPLIED)
    assert svc.is_legal_move(svc.REPLIED, svc.MEETING)
    assert svc.is_legal_move(svc.MEETING, svc.BILLABLE)
    assert svc.is_legal_move(svc.DROP, svc.CONTACTED)


def test_moves_map_rejects_illegal_and_skips():
    assert not svc.is_legal_move(svc.CONTACTED, svc.MEETING)  # can't skip stages
    assert not svc.is_legal_move(svc.CONTACTED, svc.BILLABLE)
    assert not svc.is_legal_move(svc.BILLABLE, svc.REPLIED)
    assert not svc.is_legal_move(svc.DROP, svc.REPLIED)
    assert not svc.is_legal_move(svc.CONTACTED, svc.CONTACTED)  # a no-op is not a move
    assert not svc.is_legal_move("bogus", svc.DROP)


# --------------------------------------------------------------------------- event normalization


def test_normalize_event_absorbs_provider_drift():
    assert svc.normalize_event("EMAIL_SENT") == svc.EMAIL_SENT
    assert svc.normalize_event("FIRST_EMAIL_SENT") == svc.EMAIL_SENT
    # the three drifting reply names all collapse to one internal type (R3).
    assert svc.normalize_event("EMAIL_REPLY") == svc.LEAD_REPLIED
    assert svc.normalize_event("LEAD_REPLIED") == svc.LEAD_REPLIED
    assert svc.normalize_event("EMAIL_REPLIED") == svc.LEAD_REPLIED
    assert svc.normalize_event("EMAIL_BOUNCE") == svc.LEAD_BOUNCED
    assert svc.normalize_event("LEAD_UNSUBSCRIBED") == svc.LEAD_UNSUBSCRIBED
    # case/space-insensitive.
    assert svc.normalize_event("  email_reply ") == svc.LEAD_REPLIED
    # unknown → None (stored raw, never moved, never a 5xx).
    assert svc.normalize_event("SOME_FUTURE_EVENT") is None
    assert svc.normalize_event(None) is None


def test_all_fixtures_normalize_to_known_types():
    for f, expected in [
        ("email_sent_seq1.json", svc.EMAIL_SENT),
        ("email_sent_seq2.json", svc.EMAIL_SENT),
        ("email_reply.json", svc.LEAD_REPLIED),
        ("email_bounce.json", svc.LEAD_BOUNCED),
        ("lead_unsubscribed.json", svc.LEAD_UNSUBSCRIBED),
    ]:
        assert svc.normalize_event(_load(f)["event_type"]) == expected


def test_real_bounce_fixture_ingest_fields():
    """`email_bounce.json` is the REAL Smartlead EMAIL_BOUNCE (captured live 2026-07-11: a genuine
    'address not found' hard bounce). Pin the fields the ingest path actually reads so a provider
    shape drift is caught: lead-id lives in `sl_email_lead_id` (bug #4), timestamp is tz-aware UTC,
    and the dedupe key is the derived hash (bug #5 — no per-event id in the payload)."""
    p = _load("email_bounce.json")
    assert p["event_type"] == "EMAIL_BOUNCE" and p.get("is_bounced") is True
    assert p["sl_email_lead_id"] == "4155843310"  # the field webhooks._resolve_lead reads
    dt = svc.parse_occurred_at(p)
    assert dt is not None and dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0
    assert svc.dedupe_key(p).startswith("sha256:")  # no sl_event_id/event_id → derived hash


def test_real_unsub_fixture_ingest_fields():
    """`lead_unsubscribed.json` is the REAL LEAD_UNSUBSCRIBED (captured live 2026-07-11 via the
    master-inbox opt-out). Two shape gotchas vs the other events: (1) NO `sl_email_lead_id` → the
    lead must resolve by EMAIL (`lead_email`/`to_email`); (2) the timestamp is `Z`-suffixed
    (`…940Z`), not `+00:00` — `parse_occurred_at` must still land on UTC."""
    p = _load("lead_unsubscribed.json")
    assert p["event_type"] == "LEAD_UNSUBSCRIBED"
    assert "sl_email_lead_id" not in p  # unsub carries no lead-id → email resolution
    assert "jason.tse@getholdslot.com" in svc.lead_emails(p)  # what _resolve_lead + writeback use
    dt = svc.parse_occurred_at(p)  # 14:46:19.940Z
    assert dt is not None and dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0


# --------------------------------------------------------------------------- dedupe key


def test_dedupe_key_derives_stable_hash_when_no_provider_id():
    p = _load("email_reply.json")
    assert p.get("sl_event_id") is None  # documented shape carries no unique id
    k1 = svc.dedupe_key(p)
    k2 = svc.dedupe_key(dict(p))  # identical retry payload → identical key
    assert k1 == k2 and k1.startswith("sha256:")


def test_dedupe_key_distinguishes_distinct_events():
    seq1, seq2 = _load("email_sent_seq1.json"), _load("email_sent_seq2.json")
    assert svc.dedupe_key(seq1) != svc.dedupe_key(seq2)  # different seq + ts → different key
    reply = _load("email_reply.json")
    assert svc.dedupe_key(reply) != svc.dedupe_key(seq1)  # different event_type → different key


def test_dedupe_key_prefers_real_provider_id():
    p = {"sl_event_id": "evt_777", "campaign_id": 1, "to_email": "a@b.com"}
    assert svc.dedupe_key(p) == "evt_777"  # a real id wins over the derived hash


def test_dedupe_key_ignores_email_message_id():
    """`message_id` is the email's RFC Message-ID (shared across sent/open/click of that email),
    NOT a per-event id — it must NOT become the dedupe key, or distinct event types collide."""
    base = {"campaign_id": 1, "to_email": "a@b.com", "message_id": "<m-1@x>", "sequence_number": 1}
    sent = svc.dedupe_key({**base, "event_type": "EMAIL_SENT"})
    opened = svc.dedupe_key({**base, "event_type": "EMAIL_OPEN"})
    assert sent.startswith("sha256:")  # derived hash, not the message_id
    assert sent != opened  # same email/message_id, different event type → distinct keys


# --------------------------------------------------------------------------- payload reads


def test_sequence_number_and_timestamp():
    assert svc.sequence_number(_load("email_sent_seq2.json")) == 2
    assert svc.sequence_number({"sequence_number": None}) is None
    dt = svc.parse_occurred_at(_load("email_reply.json"))
    assert dt is not None and dt.tzinfo is not None and dt.utcoffset().total_seconds() == 0
    assert svc.parse_occurred_at({}) is None  # absent → caller falls back to now()


def test_lead_emails_collects_both_directions():
    # both from/to are collected + deduped so the resolver matches the campaign's known lead either
    # way. Real EMAIL_REPLY: from = our sender (jason.wong@), sl_lead_email/to = the lead.
    reply = _load("email_reply.json")
    emails = svc.lead_emails(reply)
    assert "jason.tse@getholdslot.com" in emails  # the lead who replied
    sent = _load("email_sent_seq1.json")
    assert "jason@getholdslot.com" in svc.lead_emails(sent)  # the (bounced) send recipient


def test_reply_handle_present_in_real_reply_confirms_verdict2():
    """Verdict 2 CONFIRMED — the REAL EMAIL_REPLY (captured live 2026-07-11) carries BOTH `stats_id`
    and `message_id`, so reply-to-thread path-a works; master-inbox (R4-b) is a fallback."""
    h = svc.reply_handle(_load("email_reply.json"))
    assert h["email_stats_id"] == "fca6664d-1575-4048-82af-e93b1c9cca02"
    assert h["reply_message_id"].endswith("@mail.gmail.com>")  # the inbound reply's Message-ID
    assert "testing" in h["reply_body"]
    # …and when a payload omits them → None so E5 recovers via master-inbox (R4-b).
    h2 = svc.reply_handle({"reply_body": "hi"})
    assert h2["email_stats_id"] is None and h2["reply_message_id"] is None
    h3 = svc.reply_handle({"stats_id": "s1", "message_id": "<m1>", "reply_body": "hi"})
    assert h3["email_stats_id"] == "s1" and h3["reply_message_id"] == "<m1>"


def test_parse_inbox_handle_recovers_from_master_inbox():
    """R4-b — the master-inbox response yields the handle for the matching lead, digging into
    message_history[] when the top-level row omits it."""
    resp = {
        "data": [
            {"from_email": "other@x.com", "stats_id": "nope"},
            {
                "from_email": "Dana@Northwind.com",
                "message_history": [
                    {"type": "SENT", "message_id": "<out>"},
                    {"type": "REPLY", "stats_id": "st-9", "message_id": "<in-9>"},
                ],
            },
        ]
    }
    got = svc.parse_inbox_handle(resp, "dana@northwind.com")
    assert got == {"email_stats_id": "st-9", "reply_message_id": "<in-9>"}
    # a lead with no matching row → {} (respond then surfaces "no handle yet").
    assert svc.parse_inbox_handle(resp, "ghost@x.com") == {}
    assert svc.parse_inbox_handle({}, "a@b.com") == {}


# --------------------------------------------------------------------------- event → stage effect


def test_email_sent_seq2_advances_contacted_to_followup():
    assert svc.event_stage_effect(svc.EMAIL_SENT, 2, svc.CONTACTED) == svc.FOLLOWUP
    # seq 1 is contacted-signal only — no move.
    assert svc.event_stage_effect(svc.EMAIL_SENT, 1, svc.CONTACTED) is None
    # never walks a replied/followup lead backwards to followup.
    assert svc.event_stage_effect(svc.EMAIL_SENT, 2, svc.REPLIED) is None
    assert svc.event_stage_effect(svc.EMAIL_SENT, 2, svc.FOLLOWUP) is None


def test_bounce_and_unsub_drop_from_anywhere_but_drop():
    assert svc.event_stage_effect(svc.LEAD_BOUNCED, 1, svc.CONTACTED) == svc.DROP
    assert svc.event_stage_effect(svc.LEAD_UNSUBSCRIBED, 1, svc.FOLLOWUP) == svc.DROP
    assert svc.event_stage_effect(svc.LEAD_UNSUBSCRIBED, 1, svc.REPLIED) == svc.DROP
    assert svc.event_stage_effect(svc.LEAD_BOUNCED, 1, svc.DROP) is None  # already dropped


def test_reply_never_auto_advances():
    # a reply is queued for human triage; it does NOT move the stage.
    assert svc.event_stage_effect(svc.LEAD_REPLIED, 1, svc.CONTACTED) is None
    assert svc.event_stage_effect(svc.LEAD_OPENED, 1, svc.CONTACTED) is None


# --------------------------------------------------------------------------- triage → stage


def test_triage_stage_positive_replied_negative_drop_else_none():
    assert svc.triage_stage(svc.TRIAGE_POSITIVE) == svc.REPLIED
    assert svc.triage_stage(svc.TRIAGE_NEGATIVE) == svc.DROP
    assert svc.triage_stage(svc.TRIAGE_OBJECTION) is None  # handled, but no stage move
    assert svc.triage_stage(svc.TRIAGE_REFERRAL) is None
    assert svc.triage_stage(svc.TRIAGE_NUDGE) is None


# --------------------------------------------------------------------------- launch helpers (E3)


def test_build_lead_payload_maps_personalization_only():
    enr = {
        "email": "Dana@Northwind.com",
        "first_name": "Dana",
        "last_name": "Reyes",
        "company": "Northwind",
        "title": "VP Ops",  # not a Smartlead field — must NOT leak
        "score_total": 18,  # internal — must NOT leak
    }
    lead = svc.build_lead_payload(enr)
    assert lead == {
        "email": "Dana@Northwind.com",
        "first_name": "Dana",
        "last_name": "Reyes",
        "company_name": "Northwind",
    }


def test_build_lead_payload_none_without_email():
    assert svc.build_lead_payload({"first_name": "X"}) is None  # no email → never pushed
    assert svc.build_lead_payload({"email": "not-an-email"}) is None


def test_chunk_respects_the_add_cap():
    assert svc.chunk([1, 2, 3], 2) == [[1, 2], [3]]
    assert len(svc.chunk(list(range(801)), svc.MAX_LEADS_PER_ADD)) == 3  # 400 + 400 + 1
    assert svc.chunk([]) == []


def test_parse_statistics_progress_reads_max_seq_per_lead():
    """E6 drift check — the statistics response → {lead_id: max seq sent}, tolerant of shape."""
    resp = {
        "data": [
            {"lead_id": 111, "sequence_number": 1},
            {"lead_id": 111, "sequence_number": 2},  # max wins
            {"sl_lead_id": 222, "sent_count": 2},  # inferred step 2 from sent_count
            {"lead_id": 333, "sequence_number": 1},
            {"no_id": True},  # skipped
        ]
    }
    got = svc.parse_statistics_progress(resp)
    assert got["111"] == 2 and got["222"] == 2 and got["333"] == 1
    # only leads at seq ≥ 2 are drift-advanced to followup.
    assert {lid for lid, seq in got.items() if seq >= 2} == {"111", "222"}
    assert svc.parse_statistics_progress({}) == {}


def test_accepted_leads_inserts_only_smartlead_accepted():
    """The insert-only-on-success money path: a lead absent from the add-leads response is skipped
    (left for the next re-launch), never inserted at `contacted`."""
    by_email = {"a@x.com": ("PA", "AP-A"), "b@x.com": ("PB", "AP-B"), "c@x.com": ("PC", "AP-C")}
    got = {"a@x.com": "111", "c@x.com": "333"}  # b was rejected/duplicate → no lead id
    out = svc.accepted_leads(by_email, got)
    assert (("PA", "AP-A"), "111") in out and (("PC", "AP-C"), "333") in out
    assert all(value != ("PB", "AP-B") for value, _ in out)  # b is NOT inserted (unsent)
    assert svc.accepted_leads(by_email, {}) == []  # nothing accepted → nothing inserted


# --------------------------------------------------------------------------- per-lead timeline (E7)


def test_describe_event_stage_moved_reads_payload():
    d, title, summary = svc.describe_event(
        svc.STAGE_MOVED, {"from": "contacted", "to": "followup", "via": "statistics_poll"}
    )
    assert d == "sys" and title == "Stage moved"
    assert summary == "contacted → followup · statistics_poll"


def test_describe_event_reply_excerpts_body_and_is_inbound():
    d, title, summary = svc.describe_event(
        svc.LEAD_REPLIED, {"reply_body": "Sounds good, send a time", "sequence_number": 1}
    )
    assert d == "in" and title == "Prospect replied"
    assert summary == "Sounds good, send a time"


def test_describe_event_sent_is_outbound_with_step():
    d, title, summary = svc.describe_event(svc.EMAIL_SENT, {"sequence_number": 2})
    assert d == "out" and title == "Email sent" and summary == "step 2"


def test_describe_event_unknown_type_falls_back():
    d, title, summary = svc.describe_event("some_future_event", None)
    assert d == "sys" and title == "Some future event" and summary == ""


# ------------------------------------------------------- sending-account resolution (E3, DB→launch)


class _FakeScalars:
    def __init__(self, vals):
        self._vals = vals

    def scalars(self):
        return self

    def all(self):
        return self._vals


class _FakeSession:
    """Minimal stand-in — records the statement, returns canned rows (no Aurora)."""

    def __init__(self, vals):
        self._vals = vals
        self.stmts: list = []

    def execute(self, stmt):
        self.stmts.append(stmt)
        return _FakeScalars(self._vals)


def test_active_sending_account_ids_coerces_and_orders():
    # Money path: the launch worker fails closed unless this returns the tenant's inbox ids. The RDS
    # Data API can hand a BigInteger back as a str — assert it's coerced to int.
    from app.domains.campaigns.launch import active_sending_account_ids

    db = _FakeSession(["20084475", 20084486])  # mixed str/int, as the Data API may return
    assert active_sending_account_ids(db, "tenant-x") == [20084475, 20084486]
    assert all(isinstance(x, int) for x in active_sending_account_ids(db, "tenant-x"))


def test_active_sending_account_ids_empty_is_empty_list():
    # No active inboxes → [] → `_do_launch` raises SmartleadError (the launch never sends blind).
    from app.domains.campaigns.launch import active_sending_account_ids

    assert active_sending_account_ids(_FakeSession([]), "tenant-x") == []


# --------------------------------------------------------------------------- unsubscribe floor


def test_smartlead_settings_always_carries_unsubscribe_text():
    """Every launch must ship a working unsubscribe link (compliance floor). The default is applied
    when the operator sets nothing, and a blank string still falls back — never an empty opt-out."""
    from app.domains.campaigns.launch import DEFAULT_UNSUBSCRIBE_TEXT, _smartlead_settings

    assert _smartlead_settings({})["unsubscribe_text"] == DEFAULT_UNSUBSCRIBE_TEXT
    empty = _smartlead_settings({"smartlead_settings": {}})
    assert empty["unsubscribe_text"] == DEFAULT_UNSUBSCRIBE_TEXT
    blank = _smartlead_settings({"smartlead_settings": {"unsubscribe_text": "   "}})
    assert blank["unsubscribe_text"] == DEFAULT_UNSUBSCRIBE_TEXT


def test_smartlead_settings_preserves_operator_overrides():
    # An operator may customize the wording + pass other Smartlead settings through untouched.
    from app.domains.campaigns.launch import _smartlead_settings

    out = _smartlead_settings(
        {"smartlead_settings": {"unsubscribe_text": "Opt out here", "send_as_plain_text": True}}
    )
    assert out["unsubscribe_text"] == "Opt out here"
    assert out["send_as_plain_text"] is True


# --------------------------------------------------------------------------- M8: variant ingest


def test_variant_label_reads_aliases_trims_and_defaults_none():
    """M8 — the per-lead A/B/C variant is read tolerantly off the send event (Smartlead echoes the
    `variant_label` we set on each seq_variant; aliases cover doc drift), trimmed to the 8-char
    `MessageVariant.key` width, and is None when absent/blank so an un-reported lead stays
    unattributed rather than mis-bucketed."""
    assert svc.variant_label({"variant_label": "A"}) == "A"
    assert svc.variant_label({"email_variant_label": " B "}) == "B"  # trimmed
    assert svc.variant_label({"variant": "C"}) == "C"
    # explicit label wins over the loose alias when both present.
    assert svc.variant_label({"variant_label": "A", "variant": "B"}) == "A"
    assert svc.variant_label({"variant_label": "TOOLONGLABEL"}) == "TOOLONGL"  # 8-char cap
    assert svc.variant_label({}) is None
    assert svc.variant_label({"variant_label": "   "}) is None  # blank → None


# --------------------------------------------------------------------------- M6: UTC-pinned ISO


def test_campaign_iso_serializer_pins_utc_z():
    """M6 — the campaigns router serializes timestamps with a `Z` (like the meetings domain), so a
    naive-UTC Data API datetime is read as an instant by the FE, not as local time. A bare
    `.isoformat()` (the old bug) shifted an HK reply to the wrong calendar day."""
    from datetime import UTC, datetime

    from app.domains.campaigns.router import _iso

    assert _iso(None) is None
    # naive-UTC (what the Data API returns) → Z-suffixed instant.
    assert _iso(datetime(2026, 7, 11, 20, 0, 0)) == "2026-07-11T20:00:00Z"
    # already-aware UTC → same instant, still Z (never `+00:00`).
    assert _iso(datetime(2026, 7, 11, 20, 0, 0, tzinfo=UTC)) == "2026-07-11T20:00:00Z"


# --------------------------------------------------------------------------- M3: PDPA writeback


class _FakeBrief:
    def __init__(self, data):
        self.data = data


class _FakeResult:
    def __init__(self, obj):
        self._obj = obj

    def scalar_one_or_none(self):
        return self._obj


class _FakeDb:
    """A DB stand-in for `_unsub_writeback` — its only query is the tenant's Brief."""

    def __init__(self, brief):
        self._brief = brief

    def execute(self, *a, **k):
        return _FakeResult(self._brief)


def test_unsub_writeback_appends_email_off_payload_list_and_string_forms():
    """M3 — the write-back resolves the address from the PAYLOAD (not the lead — an unsub carries no
    lead-id) and appends it to the Brief `doNotContact`, whether that field is a list or a legacy
    newline string, de-duping. This is the SG-PDPA honor the ingest now runs on EVERY unsubscribe,
    independent of any stage move (an unsub from a lead already at `drop` moves no stage —
    `event_stage_effect(LEAD_UNSUBSCRIBED, …, DROP) is None` — yet must still be honored)."""
    from app.domains.campaigns import webhooks

    payload = {"lead_email": "Opt.Out@Acme.com"}
    # list form
    brief = _FakeBrief({"doNotContact": ["existing@x.com"]})
    webhooks._unsub_writeback(_FakeDb(brief), "tenant-1", payload)
    assert brief.data["doNotContact"] == ["existing@x.com", "opt.out@acme.com"]  # lowercased
    # idempotent — a second identical unsub doesn't duplicate.
    webhooks._unsub_writeback(_FakeDb(brief), "tenant-1", payload)
    assert brief.data["doNotContact"].count("opt.out@acme.com") == 1
    # legacy newline-string form
    brief_s = _FakeBrief({"doNotContact": "prior@x.com"})
    webhooks._unsub_writeback(_FakeDb(brief_s), "tenant-1", payload)
    assert "opt.out@acme.com" in brief_s.data["doNotContact"]
    assert "prior@x.com" in brief_s.data["doNotContact"]


def test_unsub_writeback_noop_without_email_or_brief():
    from app.domains.campaigns import webhooks

    # no candidate email in the payload → no write (returns quietly).
    brief = _FakeBrief({"doNotContact": []})
    webhooks._unsub_writeback(_FakeDb(brief), "tenant-1", {"event_type": "LEAD_UNSUBSCRIBED"})
    assert brief.data["doNotContact"] == []
    # no Brief row → no crash.
    webhooks._unsub_writeback(_FakeDb(None), "tenant-1", {"lead_email": "x@y.com"})


# ------------------------------------------------------------------- M22 — malformed-id → 404


def test_uuid_or_404_rejects_malformed_and_parses_valid():
    """M22 — the shared path-id helper raises 404 (not 400) on a malformed id, so a bad id and a
    well-formed-but-missing id read the same; a valid id parses to a UUID."""
    import uuid as _uuid

    import pytest
    from fastapi import HTTPException

    from app.core.deps import uuid_or_404

    good = _uuid.uuid4()
    assert uuid_or_404(str(good)) == good
    with pytest.raises(HTTPException) as ei:
        uuid_or_404("not-a-uuid", "no such campaign")
    assert ei.value.status_code == 404
    assert ei.value.detail == "no such campaign"

"""Structuring enqueue race (N8) — the 0027 per-tenant partial-unique guard, DB-free.

Mirrors the scoring enqueue-race test: a fake session enforces "one queued/running research_job per
tenant" so a concurrent double-Regenerate coalesces instead of double-spending the Pro scoping call.
"""

from sqlalchemy.exc import IntegrityError

from app.domains.briefs import structuring


class _EnqueueResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RaceDb:
    """Enforces the 0027 `uq_research_job_active_tenant` rule: a commit that would leave two active
    rows for the same tenant raises IntegrityError, exactly as the DB does. `race_next_check` forces
    the pre-insert check to miss once — the lost-race window."""

    def __init__(self):
        self.jobs = []  # committed rows (real ResearchJob instances)
        self._pending = None
        self.race_next_check = False

    def _active(self):
        return next((j for j in self.jobs if j.status in ("queued", "running")), None)

    def execute(self, _stmt):  # only _active_job's select runs through enqueue_structuring
        if self.race_next_check:
            self.race_next_check = False
            return _EnqueueResult(None)  # simulate: checked before the winner committed
        return _EnqueueResult(self._active())

    def add(self, job):
        self._pending = job

    def commit(self):
        job = self._pending
        self._pending = None
        if job is None:
            return
        active = (j for j in self.jobs if j.status in ("queued", "running"))
        if any(j.tenant_id == job.tenant_id for j in active):
            raise IntegrityError("INSERT research_job", {}, Exception("duplicate active job"))
        self.jobs.append(job)

    def rollback(self):
        self._pending = None

    def refresh(self, job):
        if job.id is None:
            job.id = f"job-{len(self.jobs)}"


def test_enqueue_structuring_first_job_inserts_and_dispatches(monkeypatch):
    dispatched = []
    monkeypatch.setattr(
        structuring, "_dispatch", lambda tid, jid, icp: dispatched.append((tid, jid, icp))
    )
    db = _RaceDb()
    job = structuring.enqueue_structuring(db, "t1", ["icp-a"])
    assert job in db.jobs and len(db.jobs) == 1
    assert dispatched == [("t1", job.id, ["icp-a"])]


def test_enqueue_structuring_coalesces_onto_active(monkeypatch):
    # A genuinely in-flight (non-stale) job is returned unchanged — the check-side coalesce.
    monkeypatch.setattr(structuring, "_reap_if_stale", lambda db, job: False)
    dispatched = []
    monkeypatch.setattr(structuring, "_dispatch", lambda *a: dispatched.append(a))
    db = _RaceDb()
    first = structuring.enqueue_structuring(db, "t1")
    dispatched.clear()
    again = structuring.enqueue_structuring(db, "t1")
    assert again is first
    assert not dispatched  # no second dispatch, no second spend
    assert len(db.jobs) == 1


def test_enqueue_structuring_race_coalesces_onto_winner(monkeypatch):
    # N8 — the lost-race window: the pre-check misses the winner, the insert hits the unique index,
    # and enqueue coalesces onto the winner rather than 500-ing.
    monkeypatch.setattr(structuring, "_dispatch", lambda *a: None)
    db = _RaceDb()
    winner = structuring.enqueue_structuring(db, "t1")
    db.race_next_check = True
    coalesced = structuring.enqueue_structuring(db, "t1")
    assert coalesced is winner
    assert len(db.jobs) == 1  # the duplicate insert was rolled back

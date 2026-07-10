"""Async scoring-job wiring (W4) — the pure, DB-free parts. The worker round-trip is dev-QA'd."""

from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError

from app.domains.prospects import scoring
from app.domains.prospects.router import SCORING_HANDLERS, _scoring_job_out


class _FakeJob:
    """A ScoringJob stand-in for the reaper (it only touches status/created_at/error/kind/id)."""

    def __init__(self, status: str, age_seconds: float, *, naive: bool = False):
        base = datetime.now(UTC)
        if naive:  # aurora-data-api can hand back a naive UTC datetime
            base = base.replace(tzinfo=None)
        self.status = status
        self.created_at = base - timedelta(seconds=age_seconds)
        self.error = None
        self.kind = "rescore_companies"
        self.id = "job-1"


class _FakeDb:
    def commit(self) -> None:  # the reaper commits the flip; nothing to persist in a unit test
        pass


def test_registry_maps_all_surfaces():
    # The worker dispatches on scoring_job.kind via this registry; every surface must be wired.
    kinds = {
        scoring.KIND_RESCORE_COMPANIES,
        scoring.KIND_RESCORE_PROSPECTS,
        scoring.KIND_ENRICH_SCORE_PROSPECTS,  # merged 'Reveal & score' (reveal-then-score, one job)
        scoring.KIND_FIND_COMPANY,
        scoring.KIND_FIND_LOOKALIKES,
        scoring.KIND_UPDATE_FIELDS,
    }
    assert kinds <= set(SCORING_HANDLERS)
    assert all(callable(SCORING_HANDLERS[k]) for k in kinds)


def test_enrich_score_handler_empty_keys_is_dbless_zero():
    # Empty identity_keys short-circuit to the zero-count contract BEFORE any DB access — so the
    # merged result shape is pinned without needing Aurora (the round-trip itself is dev-QA'd).
    from app.domains.prospects.router import run_enrich_score_prospects

    out = run_enrich_score_prospects(None, None, {"identity_keys": []})
    assert out == {
        "requested": 0,
        "enriched": 0,
        "credits_spent": 0,
        "enrich_failed": 0,
        "skipped_excluded": 0,
        "scored": 0,
        "failed": 0,
        "cost_usd": 0.0,
    }


def test_scoring_job_out_idle():
    out = _scoring_job_out(None)
    assert out.status == "idle"
    assert out.job_id is None
    assert out.result == {}


def test_handle_unknown_event_is_noop():
    # A wrong sub-kind is logged and ignored — never dispatched, so no DB/session is touched.
    assert scoring.handle_job_event({scoring.JOB_EVENT_KEY: "something_else"}) == {"ok": True}


# ---------------------------------------------------------------- stale-job reaper (zombie guard)


def test_reaper_flips_stale_running_job_to_error():
    # A worker hard-killed by the Lambda timeout leaves the job `running` forever; the reaper flips
    # it to `error` so the poll settles and enqueue is no longer blocked.
    job = _FakeJob("running", scoring.MAX_JOB_AGE_SECONDS + 30)
    assert scoring._reap_if_stale(_FakeDb(), job) is True
    assert job.status == "error"
    assert "timed out" in (job.error or "")


def test_reaper_leaves_fresh_active_job_alone():
    # A job still within a possible worker lifetime must keep running (no false reap mid-scoring).
    job = _FakeJob("running", 10)
    assert scoring._reap_if_stale(_FakeDb(), job) is False
    assert job.status == "running"


def test_reaper_ignores_terminal_jobs():
    # `done`/`error` are terminal — age is irrelevant, never re-touched.
    for status in ("done", "error"):
        job = _FakeJob(status, scoring.MAX_JOB_AGE_SECONDS + 999)
        assert scoring._reap_if_stale(_FakeDb(), job) is False
        assert job.status == status


def test_reaper_handles_naive_created_at():
    # A naive UTC created_at (from aurora-data-api) must not raise on the tz-aware subtraction.
    job = _FakeJob("queued", scoring.MAX_JOB_AGE_SECONDS + 30, naive=True)
    assert scoring._reap_if_stale(_FakeDb(), job) is True
    assert job.status == "error"


def test_max_job_age_exceeds_lambda_timeout():
    # The reaper must never fire before the worker's own hard timeout (300s in lambda.tf), or it
    # would kill a job that is legitimately still scoring.
    assert scoring.MAX_JOB_AGE_SECONDS > 300


# ------------------------------------------------------ enqueue race (0027 partial-unique, R9)


class _EnqueueResult:
    def __init__(self, value):
        self._value = value

    def scalar_one_or_none(self):
        return self._value


class _RaceDb:
    """Fake session enforcing the 0027 'one queued/running job per (tenant, kind)' partial-unique
    rule: a commit that would leave two active rows for the same key raises IntegrityError, exactly
    as the DB does. Real ScoringJob instances flow through (the fake ignores the SQL statement, so
    `select(ScoringJob)` still constructs against the real mapped class). `race_next_check` forces
    the pre-insert check to miss — the lost-race window."""

    def __init__(self):
        self.jobs = []  # committed rows (real ScoringJob instances)
        self._pending = None
        self.race_next_check = False

    def _active(self):
        return next((j for j in self.jobs if j.status in ("queued", "running")), None)

    def execute(self, _stmt):  # only ever _active_job's select runs through enqueue_scoring
        if self.race_next_check:
            self.race_next_check = False
            return _EnqueueResult(None)  # simulate: we checked before the winner committed
        return _EnqueueResult(self._active())

    def add(self, job):
        self._pending = job

    def commit(self):
        job = self._pending
        self._pending = None
        if job is None:
            return
        if any(
            j.status in ("queued", "running")
            and j.tenant_id == job.tenant_id
            and j.kind == job.kind
            for j in self.jobs
        ):
            raise IntegrityError("INSERT scoring_job", {}, Exception("duplicate active job"))
        self.jobs.append(job)

    def rollback(self):
        self._pending = None

    def refresh(self, job):
        if job.id is None:
            job.id = f"job-{len(self.jobs)}"


def test_enqueue_first_job_inserts_and_dispatches(monkeypatch):
    dispatched = []
    monkeypatch.setattr(scoring, "_dispatch", lambda tid, jid: dispatched.append((tid, jid)))

    db = _RaceDb()
    job = scoring.enqueue_scoring(db, "t1", "rescore_companies", {"a": 1})
    assert job in db.jobs and len(db.jobs) == 1
    assert dispatched == [("t1", job.id)]


# ------------------------------------------------------ worker lifecycle (atomic claim, R3)

_TID = "11111111-1111-1111-1111-111111111111"
_JID = "22222222-2222-2222-2222-222222222222"


class _WorkerJob:
    def __init__(self, status="queued"):
        self.id = _JID
        self.kind = scoring.KIND_RESCORE_COMPANIES
        self.params: dict = {}
        self.status = status


class _WorkerUpdateResult:
    def __init__(self, rowcount):
        self.rowcount = rowcount


class _WorkerDb:
    """Fake session for run_scoring_job — scripts the rowcount of each UPDATE (claim, then the
    guarded terminal write) so the reaped/not-claimable branches run without Aurora."""

    def __init__(self, job, rowcounts):
        self._job = job
        self._rowcounts = list(rowcounts)
        self.executed = 0

    def get(self, _model, _jid):
        return self._job

    def execute(self, _stmt):
        rc = self._rowcounts[self.executed] if self.executed < len(self._rowcounts) else 0
        self.executed += 1
        return _WorkerUpdateResult(rc)

    def commit(self):
        pass

    def rollback(self):
        pass

    def close(self):
        pass


def test_worker_aborts_when_job_not_claimable(monkeypatch):
    # A reaped/duplicate job: the atomic claim UPDATE matches 0 rows, so the worker aborts before
    # running any handler — no double-run (== no double-spend), no terminal overwrite.
    ran = []
    monkeypatch.setitem(
        SCORING_HANDLERS, scoring.KIND_RESCORE_COMPANIES,
        lambda db, tid, params: ran.append(1) or {},
    )
    db = _WorkerDb(_WorkerJob(status="error"), rowcounts=[0])  # claim matches nothing
    scoring.run_scoring_job(_TID, _JID, session_factory=lambda: db)
    assert ran == []  # handler never ran
    assert db.executed == 1  # only the claim UPDATE — no terminal write attempted


def test_worker_does_not_resurrect_reaped_job(monkeypatch):
    # The claim succeeds and the handler runs, but the job was reaped to `error` mid-run: the `done`
    # finalize (guarded WHERE status='running') matches 0 rows and must NOT overwrite the terminal
    # state — the R3 anti-resurrection guard. No exception, and no third write.
    ran = []
    monkeypatch.setitem(
        SCORING_HANDLERS, scoring.KIND_RESCORE_COMPANIES,
        lambda db, tid, params: ran.append(1) or {"scored": 1},
    )
    db = _WorkerDb(_WorkerJob(status="queued"), rowcounts=[1, 0])  # claim ok, done-write no-ops
    scoring.run_scoring_job(_TID, _JID, session_factory=lambda: db)
    assert ran == [1]  # handler ran exactly once
    assert db.executed == 2  # claim + one guarded finalize attempt (which wrote nothing)


def test_enqueue_race_coalesces_onto_winner(monkeypatch):
    # Two concurrent POSTs both pass the check-then-insert; the DB partial-unique index rejects the
    # loser's commit, and enqueue_scoring must coalesce onto the winner — one job row, no double
    # dispatch (== no double-spend).
    dispatched = []
    monkeypatch.setattr(scoring, "_dispatch", lambda tid, jid: dispatched.append((tid, jid)))

    db = _RaceDb()
    winner = scoring.enqueue_scoring(db, "t1", "rescore_companies", {})
    assert len(db.jobs) == 1 and len(dispatched) == 1

    db.race_next_check = True  # the loser missed the winner in its pre-insert check
    loser = scoring.enqueue_scoring(db, "t1", "rescore_companies", {})
    assert loser is winner  # coalesced onto the in-flight job
    assert len(db.jobs) == 1  # the loser's row never landed
    assert len(dispatched) == 1  # and no second worker was dispatched

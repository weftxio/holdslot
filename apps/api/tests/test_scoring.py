"""Async scoring-job wiring (W4) — the pure, DB-free parts. The worker round-trip is dev-QA'd."""

from datetime import UTC, datetime, timedelta

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


def test_registry_maps_all_five_surfaces():
    # The worker dispatches on scoring_job.kind via this registry; every surface must be wired.
    kinds = {
        scoring.KIND_RESCORE_COMPANIES,
        scoring.KIND_RESCORE_PROSPECTS,
        scoring.KIND_FIND_COMPANY,
        scoring.KIND_FIND_LOOKALIKES,
        scoring.KIND_UPDATE_FIELDS,
    }
    assert kinds <= set(SCORING_HANDLERS)
    assert all(callable(SCORING_HANDLERS[k]) for k in kinds)


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

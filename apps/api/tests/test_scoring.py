"""Async scoring-job wiring (W4) — the pure, DB-free parts. The worker round-trip is dev-QA'd."""

from app.domains.prospects import scoring
from app.domains.prospects.router import SCORING_HANDLERS, _scoring_job_out


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

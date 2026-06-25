import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError
from starlette.requests import Request

from app.main import _db_error_handler, app

client = TestClient(app)


def test_health_ok():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}


def test_request_id_is_generated_and_echoed():
    # RequestContextMiddleware (W3) stamps every response with an X-Request-ID …
    r = client.get("/health")
    assert r.headers.get("x-request-id")
    # … and echoes a caller-supplied one verbatim (so a client can correlate its own id).
    r2 = client.get("/health", headers={"X-Request-ID": "trace-abc123"})
    assert r2.headers.get("x-request-id") == "trace-abc123"


def _req(path: str = "/auth/login") -> Request:
    return Request({"type": "http", "method": "POST", "path": path, "headers": []})


def test_aurora_resuming_maps_to_503():
    # W6 — a DatabaseResumingException (cold-start) surfaces as a retryable 503, not a 500.
    orig = Exception("An error occurred (DatabaseResumingException): the instance is resuming")
    exc = DBAPIError("SELECT 1", {}, orig)
    resp = asyncio.run(_db_error_handler(_req(), exc))
    assert resp.status_code == 503


def test_other_db_error_stays_500():
    # A non-resume DB error is a real failure — keep it a 500 (logged).
    exc = DBAPIError("SELECT 1", {}, Exception("relation does not exist"))
    resp = asyncio.run(_db_error_handler(_req(), exc))
    assert resp.status_code == 500

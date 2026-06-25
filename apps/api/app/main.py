"""Application entrypoint.

Config loading, the Data API engine, and the central access guard are all lazy — nothing
touches AWS at import, so SnapStart snapshots a clean app and the first post-restore
invocation initializes fresh.
"""

import contextvars
import logging
import os
import sys
import time
import uuid

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from mangum import Mangum
from sqlalchemy.exc import DBAPIError

from app.domains.auth.router import router as auth_router
from app.domains.briefs.router import router as briefs_router
from app.domains.clients.router import router as clients_router
from app.domains.icps.router import router as icps_router
from app.domains.prospects.router import router as prospects_router

log = logging.getLogger("holdslot.request")

# Request id propagated onto every log line via a contextvar + filter, set per request by
# RequestContextMiddleware. Defaults to "-" for logs emitted outside a request (cold start, jobs).
request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")


class _RequestIdFilter(logging.Filter):
    """Inject the current request id onto every record so the formatter can render it."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


class RequestContextMiddleware:
    """Pure-ASGI middleware: stamp each HTTP request with a request id (`X-Request-ID` header or a
    generated one), propagate it to logs via `request_id_var`, echo it back, emit one access line
    (method, path, status, duration), and log any unhandled exception with a traceback + that id.

    Pure-ASGI (not BaseHTTPMiddleware) so the contextvar reliably propagates to the threadpool that
    runs the sync routes.
    """

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = dict(scope.get("headers") or [])
        rid = headers.get(b"x-request-id", b"").decode("latin-1") or uuid.uuid4().hex[:12]
        token = request_id_var.set(rid)
        start = time.monotonic()
        status_holder = {"code": 500}

        async def send_wrapper(message) -> None:
            if message["type"] == "http.response.start":
                status_holder["code"] = message["status"]
                message["headers"] = [
                    *message.get("headers", []),
                    (b"x-request-id", rid.encode("latin-1")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        except Exception:
            log.exception("unhandled error: %s %s", scope.get("method"), scope.get("path"))
            raise
        finally:
            if scope.get("path") != "/health":
                log.info(
                    "%s %s -> %s %.0fms",
                    scope.get("method", "?"),
                    scope.get("path", "?"),
                    status_holder["code"],
                    (time.monotonic() - start) * 1000,
                )
            request_id_var.reset(token)


def _configure_logging() -> None:
    """Surface our `holdslot.*` INFO diagnostics in CloudWatch.

    The Lambda runtime configures the ROOT logger at WARNING, so an app `log.info(...)` (e.g. the
    per-org `people-find` diagnostic) is dropped before it reaches CloudWatch. We give the
    `holdslot` parent logger its own stdout handler at INFO and stop propagation, so app logs always
    surface without boto3/sqlalchemy INFO noise. Level overridable via HOLDSLOT_LOG_LEVEL.
    """
    level = getattr(logging, os.environ.get("HOLDSLOT_LOG_LEVEL", "INFO").upper(), logging.INFO)
    root = logging.getLogger("holdslot")
    root.setLevel(level)
    root.propagate = False
    if not any(getattr(h, "_holdslot", False) for h in root.handlers):
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)s %(name)s [%(request_id)s] %(message)s")
        )
        handler.addFilter(_RequestIdFilter())
        handler._holdslot = True  # idempotent marker (SnapStart re-imports can re-run this)
        root.addHandler(handler)


_configure_logging()

app = FastAPI(title="HoldSlot API", version="0.1.0")

# Allow the web app (local dev + Amplify) to call the API. Tighten to exact origins in prod.
_origins = os.environ.get(
    "HOLDSLOT_CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _origins if o.strip()],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# Outermost middleware (added last) — wraps CORS so the request id covers the whole request.
app.add_middleware(RequestContextMiddleware)


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — smoke-tested by the deploy step (A5)."""
    return {"status": "ok"}


@app.exception_handler(DBAPIError)
async def _db_error_handler(request: Request, exc: DBAPIError) -> JSONResponse:
    """Aurora Serverless auto-pauses to 0-ACU in dev; a request that arrives mid-resume (or while it
    re-pauses inside the wake-cache window) raises a DatabaseResumingException. Surface that as a
    clean, retryable **503** — the web app retries it behind a "waking the database…" message (W6) —
    instead of a 500 that reads as a real failure. Any other DB error stays a logged 500.
    """
    if "Resuming" in str(exc):
        log.warning("aurora resuming → 503: %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=503, content={"detail": "the database is waking up, please retry"}
        )
    log.exception("database error: %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal server error"})


app.include_router(auth_router)
app.include_router(clients_router)
app.include_router(briefs_router)
app.include_router(icps_router)
app.include_router(prospects_router)

# AWS Lambda entrypoint. Two event shapes reach this one function:
#   * API Gateway (HTTP API) requests → Mangum → FastAPI.
#   * Background-job events (self async-invoke; `{"holdslot_job": ...}`) → the worker directly,
#     OFF the 30s gateway path, so slow structuring (DeepSeek V4 Pro) can run to completion.
_asgi_handler = Mangum(app)


def handler(event, context):
    from app.domains.briefs.structuring import JOB_EVENT_KEY

    if isinstance(event, dict) and event.get(JOB_EVENT_KEY):
        # The shared event key carries a sub-kind; route to the matching worker (structuring vs.
        # the W4 scoring jobs), each running OFF the 30s gateway path.
        from app.domains.briefs.structuring import handle_job_event as handle_structuring
        from app.domains.prospects.scoring import (
            JOB_PROSPECT_SCORING,
        )
        from app.domains.prospects.scoring import (
            handle_job_event as handle_scoring,
        )

        if event.get(JOB_EVENT_KEY) == JOB_PROSPECT_SCORING:
            return handle_scoring(event)
        return handle_structuring(event)
    return _asgi_handler(event, context)

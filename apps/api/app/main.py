"""Application entrypoint.

Config loading, the Data API engine, and the central access guard are all lazy — nothing
touches AWS at import, so SnapStart snapshots a clean app and the first post-restore
invocation initializes fresh.
"""

import logging
import os
import sys

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.domains.auth.router import router as auth_router
from app.domains.briefs.router import router as briefs_router
from app.domains.clients.router import router as clients_router
from app.domains.icps.router import router as icps_router
from app.domains.prospects.router import router as prospects_router


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
        handler.setFormatter(logging.Formatter("%(levelname)s %(name)s %(message)s"))
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


@app.get("/health")
def health() -> dict[str, str]:
    """Liveness probe — smoke-tested by the deploy step (A5)."""
    return {"status": "ok"}


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
    from app.domains.briefs.structuring import JOB_EVENT_KEY, handle_job_event

    if isinstance(event, dict) and event.get(JOB_EVENT_KEY):
        return handle_job_event(event)
    return _asgi_handler(event, context)

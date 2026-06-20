"""Application entrypoint.

Config loading, the Data API engine, and the central access guard are all lazy — nothing
touches AWS at import, so SnapStart snapshots a clean app and the first post-restore
invocation initializes fresh.
"""

import os

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.domains.auth.router import router as auth_router
from app.domains.briefs.router import router as briefs_router
from app.domains.clients.router import router as clients_router
from app.domains.icps.router import router as icps_router
from app.domains.prospects.router import router as prospects_router

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

# AWS Lambda entrypoint: API Gateway (HTTP API) → Mangum → FastAPI.
handler = Mangum(app)

"""Database access over the RDS Data API.

One SQLAlchemy engine, used by both the app (runtime) and Alembic (migrations). The Data
API is stateless HTTP — no persistent connection — so it's SnapStart-safe and works
identically from a developer laptop (local AWS creds) and from Lambda (exec role). The
engine is built lazily and cached, never at import, so no AWS call happens during a
SnapStart snapshot.
"""

from __future__ import annotations

import logging
import os
import time
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

log = logging.getLogger("holdslot.db")


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def is_unique_violation(exc: BaseException) -> bool:
    """True if `exc` is a Postgres unique-violation (SQLSTATE 23505), HOWEVER the driver surfaced it
    (N29). Over psycopg SQLAlchemy raises `IntegrityError`, but the RDS Data API driver
    (aurora-data-api) can wrap it as a generic `DBAPIError`/`DatabaseError` — so match the SQLSTATE
    or the message text too, or the enqueue race would 500 on the live driver, not coalesce."""
    if isinstance(exc, IntegrityError):
        return True
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) == "23505" or getattr(orig, "pgcode", None) == "23505":
        return True
    msg = str(orig if orig is not None else exc).lower()
    return "23505" in msg or "duplicate key" in msg or "unique constraint" in msg


def is_fk_violation(exc: BaseException) -> bool:
    """True if `exc` is a Postgres foreign-key violation (SQLSTATE 23503), HOWEVER the driver
    surfaced it — same driver-drift reasoning as `is_unique_violation` (psycopg raises
    `IntegrityError`; the RDS Data API can wrap it as a generic `DBAPIError`). Lets a route turn a
    RESTRICT/cascade FK failure into a 409 instead of a raw 500 (M10)."""
    if isinstance(exc, IntegrityError):
        return True
    orig = getattr(exc, "orig", None)
    if getattr(orig, "sqlstate", None) == "23503" or getattr(orig, "pgcode", None) == "23503":
        return True
    msg = str(orig if orig is not None else exc).lower()
    return "23503" in msg or "foreign key constraint" in msg or "violates foreign key" in msg


def _engine_url_and_args() -> tuple[str, dict]:
    """Build the aurora-data-api SQLAlchemy URL + connect args from the environment.

    Required env (set by Terraform on Lambda; exported from `terraform output` locally):
      HOLDSLOT_DB_CLUSTER_ARN, HOLDSLOT_DB_SECRET_ARN, HOLDSLOT_DB_NAME
    """
    cluster_arn = os.environ["HOLDSLOT_DB_CLUSTER_ARN"]
    secret_arn = os.environ["HOLDSLOT_DB_SECRET_ARN"]
    db_name = os.environ.get("HOLDSLOT_DB_NAME", "holdslot")
    # The dialect builds its own boto3 rds-data client, which reads the region from the
    # environment (AWS_REGION is set automatically in Lambda; export it locally).
    os.environ.setdefault("AWS_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    url = f"postgresql+auroradataapi://:@/{db_name}"
    connect_args = {
        "aurora_cluster_arn": cluster_arn,
        "secret_arn": secret_arn,
    }
    return url, connect_args


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    url, connect_args = _engine_url_and_args()
    # NullPool semantics: the Data API has no connections to pool. future=True for 2.0 API.
    return create_engine(url, connect_args=connect_args, future=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)


def get_session() -> Session:
    """A new Session. FastAPI dependency wrapper lives in the app layer (A4)."""
    return _session_factory()()


_last_awake_monotonic = 0.0
_AWAKE_TTL_SECONDS = 60


def ensure_awake(session: Session, attempts: int = 8, delay_seconds: float = 8.0) -> None:
    """Wake Aurora from 0-ACU auto-pause before serving a request.

    With scale-to-zero the first call after idle raises DatabaseResumingException; retry
    with backoff until it's up. Success is cached for a minute so warm requests pay nothing.
    """
    global _last_awake_monotonic
    if time.monotonic() - _last_awake_monotonic < _AWAKE_TTL_SECONDS:
        return
    for i in range(attempts):
        try:
            session.execute(text("SELECT 1"))
            _last_awake_monotonic = time.monotonic()
            return
        except DBAPIError as e:
            if "Resuming" in str(e) and i < attempts - 1:
                log.info("Aurora resuming, retry %d/%d", i + 1, attempts)
                time.sleep(delay_seconds)
                continue
            raise

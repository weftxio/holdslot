"""Alembic environment.

Migrations run over the RDS Data API (same engine the app uses), so they work from a
laptop with local AWS creds and from CI alike — no VPC, no DB password. The app package
(`apps/api`) is added to sys.path so the models are the single schema source of truth.

Required env: HOLDSLOT_DB_CLUSTER_ARN, HOLDSLOT_DB_SECRET_ARN, HOLDSLOT_DB_NAME
(export from `terraform output`).
"""

import os
import sys
from logging.config import fileConfig

from alembic import context

# Make the `app` package importable (apps/api is two levels up from infra/alembic).
_API_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "apps", "api"))
if _API_DIR not in sys.path:
    sys.path.insert(0, _API_DIR)

from app.core.db import Base, get_engine  # noqa: E402
import app.models  # noqa: E402,F401  (register models on Base.metadata)

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    raise RuntimeError(
        "Offline migrations are unsupported over the Data API — run `alembic upgrade` online."
    )


def run_migrations_online() -> None:
    connectable = get_engine()
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()

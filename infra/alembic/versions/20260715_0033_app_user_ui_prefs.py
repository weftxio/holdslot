"""Add app_user.ui_prefs — per-user console UI preferences (account-scoped)

Revision ID: 0033_app_user_ui_prefs
Revises: 0032_outreach_occurred_index
Create Date: 2026-07-15

A single additive JSONB column on the global identity table `app_user`, defaulting to '{}'. It
holds per-user console UI preferences (first consumer: the sidebar collapse/expand state) so the
choice follows the user across devices/browsers, not just one localStorage. An opaque bag keeps
future UI toggles migration-free. Zero new AWS resources; deploy-first-safe (nullable=False with a
server_default backfills existing rows); fully reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0033_app_user_ui_prefs"
down_revision: str | None = "0032_outreach_occurred_index"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "app_user",
        sa.Column(
            "ui_prefs",
            postgresql.JSONB(),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("app_user", "ui_prefs")

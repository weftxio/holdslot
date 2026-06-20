"""phase C (S2) — tenant.seed_limit

Revision ID: 0006_tenant_seed_limit
Revises: 0005_phase_c
Create Date: 2026-06-20

Adds the `seed_limit` column to `tenant`: the per-client AI-sourcing knob (how many passed-fit
prospects anchor each round), edited in the Sourcing-settings modal. A scalar config, defaulted
to 10 so existing tenants stay valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_tenant_seed_limit"
down_revision: str | None = "0005_phase_c"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "tenant",
        sa.Column(
            "seed_limit",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("10"),
        ),
    )


def downgrade() -> None:
    op.drop_column("tenant", "seed_limit")

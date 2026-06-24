"""phase B (S1) — research_spec.icp_suggestions

Revision ID: 0004_icp_suggestions
Revises: 0003_phase_b
Create Date: 2026-06-17

Adds the `icp_suggestions` JSONB column to `research_spec`: proposed ICPs the structuring
LLM infers from the client's existing-customer list (the realest proof of who pays) when the
paying customers diverge from every stated ICP. Stored alongside `gaps`, never inside the
targeting `spec`. Defaults to an empty array so existing rows stay valid.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_icp_suggestions"
down_revision: str | None = "0003_phase_b"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.add_column(
        "research_spec",
        sa.Column(
            "icp_suggestions",
            JSONB,
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )


def downgrade() -> None:
    op.drop_column("research_spec", "icp_suggestions")

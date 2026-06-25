"""W4 — scoring_job: async fit-scoring job tracker

Revision ID: 0015_scoring_job
Revises: 0014_perf_indexes_fit_reason
Create Date: 2026-06-25

The five scoring-bearing surfaces (find-company, find-lookalikes, company/prospect rescore, company
field refresh) fan out one fit-scoring LLM call per row; a large batch exceeds the API Gateway 30s
cap, and the prior client-driven chunk loop dies if the tab closes. So scoring moves async (W4,
docs/initial-build-plan.md -> Modularization + W0-W8): a kick-off endpoint inserts a `queued` row here and fires a background
worker (Lambda self async-invoke; a thread locally), which flips it `running`→`done`/`error` and
records per-run counts on `result`. `kind` names the surface; `params` is the original request body.
Mirrors `research_job` (0009); `updated_at` is kept fresh by the ORM `onupdate`, no trigger needed.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0015_scoring_job"
down_revision: str | None = "0014_perf_indexes_fit_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_JSON = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "scoring_job",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(32), nullable=False),  # which scoring surface
        sa.Column("params", JSONB, nullable=False, server_default=EMPTY_JSON),  # original body
        # queued → running → done | error
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("result", JSONB, nullable=False, server_default=EMPTY_JSON),  # per-run counts
        sa.Column("error", sa.Text, nullable=True),  # set on error
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_scoring_job_tenant_kind", "scoring_job", ["tenant_id", "kind"])


def downgrade() -> None:
    op.drop_index("ix_scoring_job_tenant_kind", table_name="scoring_job")
    op.drop_table("scoring_job")

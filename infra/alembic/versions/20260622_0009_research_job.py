"""phase B — research_job: async Brief→ResearchSpec structuring job tracker

Revision ID: 0009_research_job
Revises: 0008_company_website
Create Date: 2026-06-22

DeepSeek V4 Pro scoping (thinking + web search) reasons ~55-76s — past the API Gateway HTTP-API
hard 30s cap. So structuring is async: `POST /brief/structure` inserts a `queued` row here and
fires a background worker (Lambda self async-invoke; a thread locally); the worker runs the LLM,
inserts the next `research_spec` version, and updates this row to `done`/`error`. The UI polls
`GET /brief/structure/status` until terminal. Phase-B infra (0010 renames sourcing_doc→prompt;
the Apollo migration is 0011).
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0009_research_job"
down_revision: str | None = "0008_company_website"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")


def upgrade() -> None:
    op.create_table(
        "research_job",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        # queued → running → done | error
        sa.Column("status", sa.String(16), nullable=False, server_default="queued"),
        sa.Column("spec_version", sa.Integer, nullable=True),  # set on done
        sa.Column("error", sa.Text, nullable=True),  # set on error
        sa.Column(
            "llm_call_id", UUID, sa.ForeignKey("llm_call.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_research_job_tenant_id", "research_job", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_research_job_tenant_id", table_name="research_job")
    op.drop_table("research_job")

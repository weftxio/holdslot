"""phase C (S2) — company-first two-stage: company table + prospect.company_id

Revision ID: 0007_phase_c_companies
Revises: 0006_tenant_seed_limit
Create Date: 2026-06-20

The one structural change for the company-first, two-stage flow (Find Companies → Find People):
a `company` stage-1 discovery table (per domain × tenant, unique) and a nullable
`prospect.company_id` FK linking each person back to the company it was sourced from. No data
backfill — existing single-stage prospects keep `company_id = NULL`.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0007_phase_c_companies"
down_revision: str | None = "0006_tenant_seed_limit"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_OBJ = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "company",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("icp_id", UUID, sa.ForeignKey("icp.id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("domain", sa.String(255), nullable=False),
        sa.Column("linkedin_url", sa.String(512), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("industry", sa.String(255), nullable=True),
        sa.Column("size", sa.String(64), nullable=True),
        sa.Column("country", sa.String(128), nullable=True),
        sa.Column("fit_score", sa.Integer, nullable=True),
        sa.Column("fit_tier", sa.String(32), nullable=True),
        sa.Column("fit_reason", sa.Text, nullable=True),
        sa.Column("fit_components", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("evidence", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="discovered"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_company_tenant_domain"),
    )
    op.create_index("ix_company_tenant_id", "company", ["tenant_id"])
    op.create_index("ix_company_domain", "company", ["domain"])

    op.add_column(
        "prospect",
        sa.Column(
            "company_id",
            UUID,
            sa.ForeignKey("company.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("prospect", "company_id")
    op.drop_index("ix_company_domain", table_name="company")
    op.drop_index("ix_company_tenant_id", table_name="company")
    op.drop_table("company")

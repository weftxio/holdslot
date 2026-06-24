"""phase B (S1) — targeting: brief, icp, llm_call, research_spec

Revision ID: 0003_phase_b
Revises: 0002_seed
Create Date: 2026-06-12

Tenant-scoped JSONB documents (brief/icp) + append-only telemetry (llm_call) and the
versioned ResearchSpec contract. Brief/icp `data` is opaque JSONB so form-field changes
never need a migration; the ResearchSpec is the locked v1 targeting contract.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0003_phase_b"
down_revision: str | None = "0002_seed"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")


def _tenant_fk() -> sa.ForeignKey:
    # A fresh ForeignKey per column — one FK object cannot be shared across columns.
    return sa.ForeignKey("tenant.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "brief",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.UniqueConstraint("tenant_id", name="uq_brief_tenant"),
    )
    op.create_index("ix_brief_tenant_id", "brief", ["tenant_id"])

    op.create_table(
        "icp",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("tag", sa.String(255), nullable=False, server_default=""),
        sa.Column("data", JSONB, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
    )
    op.create_index("ix_icp_tenant_id", "icp", ["tenant_id"])

    op.create_table(
        "llm_call",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("purpose", sa.String(64), nullable=False),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("input_tokens", sa.Integer, nullable=True),
        sa.Column("output_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Numeric(14, 8), nullable=True),
        sa.Column("latency_ms", sa.Integer, nullable=True),
        sa.Column("retries", sa.Integer, nullable=False, server_default="0"),
        sa.Column("raw", JSONB, nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
    )
    op.create_index("ix_llm_call_tenant_id", "llm_call", ["tenant_id"])
    op.create_index("ix_llm_call_purpose", "llm_call", ["purpose"])

    op.create_table(
        "research_spec",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("spec", JSONB, nullable=False),
        sa.Column("gaps", JSONB, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.Column("model", sa.String(128), nullable=True),
        sa.Column(
            "llm_call_id",
            UUID,
            sa.ForeignKey("llm_call.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.UniqueConstraint(
            "tenant_id", "version", name="uq_research_spec_tenant_version"
        ),
    )
    op.create_index("ix_research_spec_tenant_id", "research_spec", ["tenant_id"])

    # Keep updated_at fresh even for raw-SQL UPDATEs (the ORM also sets it via onupdate).
    op.execute(
        """
        CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
        """
    )
    for tbl in ("brief", "icp"):
        op.execute(
            f"CREATE TRIGGER trg_{tbl}_updated_at BEFORE UPDATE ON {tbl} "
            f"FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
        )


def downgrade() -> None:
    for tbl in ("brief", "icp"):
        op.execute(f"DROP TRIGGER IF EXISTS trg_{tbl}_updated_at ON {tbl};")
    op.execute("DROP FUNCTION IF EXISTS set_updated_at();")
    op.drop_index("ix_research_spec_tenant_id", table_name="research_spec")
    op.drop_table("research_spec")
    op.drop_index("ix_llm_call_purpose", table_name="llm_call")
    op.drop_index("ix_llm_call_tenant_id", table_name="llm_call")
    op.drop_table("llm_call")
    op.drop_index("ix_icp_tenant_id", table_name="icp")
    op.drop_table("icp")
    op.drop_index("ix_brief_tenant_id", table_name="brief")
    op.drop_table("brief")

"""Phase D (S3) — Sendout batch + approval (batch, prospect_approval, approval_link, template)

Revision ID: 0016_phase_d_batch_approval
Revises: 0015_scoring_job
Create Date: 2026-06-25

The revenue precondition (docs/initial-build-plan.md -> Phase D): group enriched Phase-C prospects
into a `batch`, send the client a tokenized, expiring, MASKED approval link (`approval_link`, an
opaque-hash token mirroring `password_reset` — validity checked on read, no scheduler), and record
each per-prospect decision as the append-only `prospect_approval` row S7 bills against.
`approval_template` is the thin per-tenant sendout-copy override (mirrors `brief`). Total/approved
counts are DERIVED from `prospect_approval`, never stored. Same conventions as A/B/C (uuid PK,
`tenant_id` CASCADE, timestamptz, string status — no DB enum); NO new AWS resources.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0016_phase_d_batch_approval"
down_revision: str | None = "0015_scoring_job"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_JSON = sa.text("'{}'::jsonb")


def _tenant_fk() -> sa.Column:
    fk = sa.ForeignKey("tenant.id", ondelete="CASCADE")
    return sa.Column("tenant_id", UUID, fk, nullable=False)


def upgrade() -> None:
    # batch — the unit the client approves; counts derived from prospect_approval.
    op.create_table(
        "batch",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column("icp_id", UUID, sa.ForeignKey("icp.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        # draft → sent → approved | changes_requested
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index(
        "ix_batch_tenant_created", "batch", ["tenant_id", sa.text("created_at DESC")]
    )

    # prospect_approval ⭐ — the billable record; one append-only row per (prospect × batch).
    op.create_table(
        "prospect_approval",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "batch_id", UUID, sa.ForeignKey("batch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "prospect_id", UUID, sa.ForeignKey("prospect.id", ondelete="CASCADE"), nullable=False
        ),
        # pending → approved | removed (request_changes is a batch-level status, not per-prospect)
        sa.Column("decision", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        # (batch_id, prospect_id) UNIQUE covers batch_id lookups via its leftmost prefix.
        sa.UniqueConstraint(
            "batch_id", "prospect_id", name="uq_prospect_approval_batch_prospect"
        ),
    )
    op.create_index("ix_prospect_approval_tenant_id", "prospect_approval", ["tenant_id"])

    # approval_link — mirrors password_reset (opaque token stored hashed, validity checked on read).
    op.create_table(
        "approval_link",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "batch_id", UUID, sa.ForeignKey("batch.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("recipient_email", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_approval_link_batch_id", "approval_link", ["batch_id"])

    # approval_template — one sendout-copy doc per tenant (mirrors brief); a code default serves
    # until the founder edits it.
    op.create_table(
        "approval_template",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column("data", JSONB, nullable=False, server_default=EMPTY_JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", name="uq_approval_template_tenant"),
    )


def downgrade() -> None:
    op.drop_table("approval_template")
    op.drop_index("ix_approval_link_batch_id", table_name="approval_link")
    op.drop_table("approval_link")
    op.drop_index("ix_prospect_approval_tenant_id", table_name="prospect_approval")
    op.drop_table("prospect_approval")
    op.drop_index("ix_batch_tenant_created", table_name="batch")
    op.drop_table("batch")

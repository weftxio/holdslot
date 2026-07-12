"""Phase G (S7) — Stripe billing (subscription, billing_event, meeting.billed_at)

Revision ID: 0031_stripe_subscription
Revises: 0030_phase_f_meeting
Create Date: 2026-07-13

The billing metering layer (docs/initial-build-plan.md → §GS; docs/data-schema.md → Phase G).
**Pre-built + dormant per GD-10:** written now, but APPLIED only after the founder's test-mode
`stripe_smoke_live.py` probe pins the Stripe contract (FR-7) — exactly the E0 pattern. It ships
dormant because no tenant has a `subscription` row until the first signup, so the on-read billing
sweep + the enrich-cap guard are both no-ops for tenant #0.

One EXPAND migration (migrate-first, deploy-first-safe — nothing the live product reads is touched):
  * `subscription`   — one billing row per paying tenant (unique `tenant_id`): the Stripe
                       customer/subscription handles, plan-derived caps + the month usage counter
                       (the GS4 enrich-cap guard), and the Stripe-mirrored `status`. tenant #0 gets
                       NO row (dogfood billing stays computed-only).
  * `billing_event`  — append-only Stripe webhook log + the idempotency store (GS5); mirrors
                       `outreach_event` (raw event stored, deduped on `stripe_event_id`).
  * `meeting.billed_at` — the charge-emitted stamp (GS3 sweep claim). `amount`/`is_billable`/
                       `billing_chip` are UNCHANGED — billing stays derived on read; this column is
                       only the "a meter event was emitted for this meeting" trigger record.

Same conventions as A–F: uuid PK, `tenant_id` CASCADE, timestamptz, string status (no DB enum), zero
new AWS resources. Fully reversible: downgrade drops the column then the two tables in FK order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0031_stripe_subscription"
down_revision: str | None = "0030_phase_f_meeting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
TRUE = sa.text("true")
EMPTY_OBJ = sa.text("'{}'::jsonb")


def _tenant_fk(*, nullable: bool = False) -> sa.Column:
    fk = sa.ForeignKey("tenant.id", ondelete="CASCADE")
    return sa.Column("tenant_id", UUID, fk, nullable=nullable)


def upgrade() -> None:
    # subscription — one billing row per paying tenant (unique tenant_id). tenant #0 gets no row.
    op.create_table(
        "subscription",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column("plan", sa.String(16), nullable=False, server_default="free"),
        sa.Column("stripe_customer_id", sa.String(64), nullable=True),
        sa.Column("stripe_subscription_id", sa.String(64), nullable=True),
        sa.Column("activation_paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("enrichment_cap", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("icp_limit", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_month_usage", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("usage_month", sa.String(7), nullable=True),  # YYYY-MM (UTC)
        sa.Column("admin_quota_override", sa.Integer(), nullable=True),
        sa.Column("overage_enabled", sa.Boolean(), nullable=False, server_default=TRUE),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", name="uq_subscription_tenant"),
    )

    # billing_event — append-only Stripe webhook log + dedupe (mirror of outreach_event).
    op.create_table(
        "billing_event",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(nullable=True),  # resolved off the customer id; NULL if unknown (still stored)
        sa.Column("stripe_event_id", sa.String(64), nullable=False, unique=True),
        sa.Column("type", sa.String(64), nullable=False),
        sa.Column("payload", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_billing_event_tenant_id", "billing_event", ["tenant_id"])

    # meeting.billed_at — the GS3 charge-emitted stamp (nullable; NULL for every existing row).
    op.add_column("meeting", sa.Column("billed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("meeting", "billed_at")
    op.drop_index("ix_billing_event_tenant_id", table_name="billing_event")
    op.drop_table("billing_event")
    op.drop_table("subscription")

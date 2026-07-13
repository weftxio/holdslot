"""Wave 2 (M22) — align the outreach_event hot index with the actual ORDER BY (occurred_at)

Revision ID: 0032_outreach_occurred_index
Revises: 0031_stripe_subscription
Create Date: 2026-07-13

Two pure INDEX changes (no data, no column touched — deploy-first-safe, fully reversible):

  * `outreach_event` — the composite `ix_outreach_event_tenant_type_created` sorted its third
    column on `created_at DESC`, but EVERY consumer (reply queue, per-lead timeline, booking
    invitation lookup, performance-summary counts) filters `tenant_id`+`event_type` and orders by
    `occurred_at DESC` (the provider event time, which can differ from the ingest `created_at`).
    Swap the index to `occurred_at DESC` so those reads are index-sorted instead of table-scanned.
  * `subscription.stripe_customer_id` — the Stripe webhook resolves a subscription by this column;
    index it (dormant today — the table has 0 rows until the first signup, but the index is free).

Same conventions as A–G: zero new AWS resources; downgrade restores the created_at index + drops the
customer-id index. Ships with the Wave 2 backend; applied on the next founder backend deploy.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0032_outreach_occurred_index"
down_revision: str | None = "0031_stripe_subscription"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_index("ix_outreach_event_tenant_type_created", table_name="outreach_event")
    op.create_index(
        "ix_outreach_event_tenant_type_occurred",
        "outreach_event",
        ["tenant_id", "event_type", sa.text("occurred_at DESC")],
    )
    op.create_index(
        "ix_subscription_stripe_customer_id", "subscription", ["stripe_customer_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_subscription_stripe_customer_id", table_name="subscription")
    op.drop_index("ix_outreach_event_tenant_type_occurred", table_name="outreach_event")
    op.create_index(
        "ix_outreach_event_tenant_type_created",
        "outreach_event",
        ["tenant_id", "event_type", sa.text("created_at DESC")],
    )

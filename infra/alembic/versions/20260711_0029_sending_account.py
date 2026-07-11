"""Phase E follow-up — sending_account (per-tenant Smartlead inbox pool, out of Secrets Manager)

Revision ID: 0029_sending_account
Revises: 0028_phase_e_campaign
Create Date: 2026-07-11

Moves the Smartlead **sending-inbox ids** out of the shared `holdslot/prod/smartlead` secret and into
a tenant-scoped table (founder decision 2026-07-11, "even for MVP"). An inbox id is a reference, not a
credential — the shared `api_key` stays the only secret; the tenant→inbox mapping is config that grows
per client, so it belongs in the DB (a row per onboarding, not a secret edit + Lambda cache-bust +
redeploy). The launch worker now reads `active` rows here instead of `sl.sending_account_ids()`.

One EXPAND table (deploy-first-safe — nothing the live product reads is touched), same A–D conventions
(uuid PK, `tenant_id` CASCADE, timestamptz, string status, zero new AWS resources). Fully reversible.

Also seeds the dogfood tenant #0 (`slug='holdslot'`) with its two warmed inboxes (20084486, 20084475)
so the loop works end-to-end the moment this ships — idempotent (ON CONFLICT), tenant-scoped, and it
travels to every env where that tenant exists. Future clients are seeded through the app, NOT here.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0029_sending_account"
down_revision: str | None = "0028_phase_e_campaign"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")

# Tenant #0's two warmed Smartlead sending inboxes (founder-supplied 2026-07-11).
HOLDSLOT_INBOX_IDS = (20084486, 20084475)


def upgrade() -> None:
    op.create_table(
        "sending_account",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("smartlead_account_id", sa.BigInteger(), nullable=False),
        sa.Column("from_email", sa.String(320), nullable=True),
        sa.Column("from_name", sa.String(255), nullable=True),
        # warming · active · paused — only `active` inboxes are attached to a campaign.
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "tenant_id", "smartlead_account_id", name="uq_sending_account_tenant_smartlead"
        ),
    )
    op.create_index("ix_sending_account_tenant", "sending_account", ["tenant_id"])

    # Dogfood tenant #0 seed — idempotent, tenant-scoped. VALUES→CROSS JOIN attaches both ids to the
    # `holdslot` tenant if (and only if) it exists in this environment.
    values = ", ".join(f"({sid}::bigint)" for sid in HOLDSLOT_INBOX_IDS)
    op.execute(
        f"""
        INSERT INTO sending_account (tenant_id, smartlead_account_id, status)
        SELECT t.id, v.sid, 'active'
        FROM tenant t
        CROSS JOIN (VALUES {values}) AS v(sid)
        WHERE t.slug = 'holdslot'
        ON CONFLICT (tenant_id, smartlead_account_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.drop_index("ix_sending_account_tenant", table_name="sending_account")
    op.drop_table("sending_account")

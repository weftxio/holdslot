"""phase C — scope_override: persist the Find Settings (Step-2 people scope) per tenant

Revision ID: 0012_scope_override
Revises: 0011_apollo_ids
Create Date: 2026-06-24

The Step-2 "Find People · who to target" facets were a per-browser localStorage override, so a
saved tuning vanished on another device and a stale entry could silently shadow the AI scope. This
moves it server-side: one row per (tenant, `kind`), `params` = the opaque override merged over the
`research_spec` at find time. `kind='people'` today (the facet override); `company` (Step-1) can
reuse the same table later. Single-row UPSERT — deleting the row reverts to the AI scope. Additive;
up/down clean.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0012_scope_override"
down_revision: str | None = "0011_apollo_ids"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_OBJ = sa.text("'{}'::jsonb")


def upgrade() -> None:
    op.create_table(
        "scope_override",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "tenant_id", UUID, sa.ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("params", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "kind", name="uq_scope_override_tenant_kind"),
    )
    op.create_index("ix_scope_override_tenant_id", "scope_override", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_scope_override_tenant_id", table_name="scope_override")
    op.drop_table("scope_override")

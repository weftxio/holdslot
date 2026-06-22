"""phase C (C1) — Apollo link ids: company.apollo_org_id + prospect.apollo_person_id; -seed_limit

The two ids that physically link the find→enrich loop:
  * `company.apollo_org_id` — the Apollo organization id; the **selected** set's ids are passed as
    `organization_ids` to find-people (the Flow A→B scope link). Unique per tenant (nullable: a
    `manual` company has none; Postgres allows multiple NULLs under a unique constraint).
  * `prospect.apollo_person_id` — the `people/match` enrich key. Apollo search exposes no
    linkedin/email/domain pre-enrich, so Apollo-found rows also carry `identity_key="apollo:<id>"`.

Also drops the now-dead `tenant.seed_limit` (the AI-loop seed anchor — its model field was removed
in the Apollo-only teardown; this drops the lingering column). Additive + one drop; up/down clean.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_apollo_ids"
down_revision: str | None = "0010_prompt_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("company", sa.Column("apollo_org_id", sa.String(64), nullable=True))
    op.create_unique_constraint(
        "uq_company_tenant_apollo_org", "company", ["tenant_id", "apollo_org_id"]
    )
    op.add_column("prospect", sa.Column("apollo_person_id", sa.String(64), nullable=True))
    op.create_index(
        "ix_prospect_apollo_person_id", "prospect", ["tenant_id", "apollo_person_id"]
    )
    op.drop_column("tenant", "seed_limit")


def downgrade() -> None:
    op.add_column(
        "tenant",
        sa.Column("seed_limit", sa.Integer(), nullable=False, server_default=sa.text("10")),
    )
    op.drop_index("ix_prospect_apollo_person_id", table_name="prospect")
    op.drop_column("prospect", "apollo_person_id")
    op.drop_constraint("uq_company_tenant_apollo_org", "company", type_="unique")
    op.drop_column("company", "apollo_org_id")

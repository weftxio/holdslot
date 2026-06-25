"""perf — list-sort composite indexes, drop redundant indexes, prospect.fit_reason, so trigger

Revision ID: 0014_perf_indexes_fit_reason
Revises: 0013_split_fit_rubric
Create Date: 2026-06-25

Backend simplification plan (docs/modularization-plan.md sections 4.2/4.3, wave W1). Four
behaviour-neutral schema changes:

1. Composite list-sort indexes on `prospect` and `company`:
   `(tenant_id, fit_score DESC NULLS LAST, created_at DESC)` — matches the exact ORDER BY of the
   `/{client}/prospects` and `/{client}/companies` list feeds (prospects/router.py), so the hottest
   read stops sorting the whole tenant table in memory. DESC + NULLS LAST are explicit so the
   planner can return rows already ordered.

2. Drop 4 redundant single-column indexes — each fully covered by an existing UNIQUE constraint's
   index, and every lookup on the column is tenant-scoped (verified against router.py):
     - ix_company_domain           covered by uq_company_tenant_domain (tenant_id, domain)
     - ix_prospect_identity_key    covered by uq_prospect_tenant_identity (tenant_id, identity_key)
     - ix_brief_tenant_id          equals uq_brief_tenant (tenant_id) -- same single column
     - ix_scope_override_tenant_id covered by uq_scope_override_tenant_kind -- leftmost prefix
   They only cost write throughput on insert. (The new composite also makes ix_company_tenant_id /
   ix_prospect_tenant_id redundant via leftmost prefix — left in place here, flagged for a follow-up
   so this migration stays at the reviewed scope.)

3. prospect.fit_reason — column parity with `company.fit_reason` (a real column) so the Phase-D
   reader finds the prospect fit reason in a column, not buried in `fit_components` JSON. Nullable;
   populated on next rescore (no backfill).

4. scope_override updated_at trigger — `scope_override` is written via a raw UPSERT that bypasses
   the ORM `onupdate`, so `updated_at` went stale. Attach the existing `set_updated_at()` trigger
   (created in 0003) the same way brief/icp already have it.

Fully reversible: the downgrade drops the trigger + column + composite indexes and restores the
four single-column indexes.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0014_perf_indexes_fit_reason"
down_revision: str | None = "0013_split_fit_rubric"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 1. Composite list-sort indexes (raw SQL expresses DESC NULLS LAST unambiguously).
    op.execute(
        "CREATE INDEX ix_prospect_tenant_fit ON prospect "
        "(tenant_id, fit_score DESC NULLS LAST, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_company_tenant_fit ON company "
        "(tenant_id, fit_score DESC NULLS LAST, created_at DESC)"
    )

    # 2. Drop the four UNIQUE-covered single-column indexes.
    op.drop_index("ix_company_domain", table_name="company")
    op.drop_index("ix_prospect_identity_key", table_name="prospect")
    op.drop_index("ix_brief_tenant_id", table_name="brief")
    op.drop_index("ix_scope_override_tenant_id", table_name="scope_override")

    # 3. prospect.fit_reason — parity with company.fit_reason.
    op.add_column("prospect", sa.Column("fit_reason", sa.String(), nullable=True))

    # 4. Keep scope_override.updated_at fresh under raw UPSERT (function exists since 0003).
    op.execute(
        "CREATE TRIGGER trg_scope_override_updated_at BEFORE UPDATE ON scope_override "
        "FOR EACH ROW EXECUTE FUNCTION set_updated_at();"
    )


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_scope_override_updated_at ON scope_override;")
    op.drop_column("prospect", "fit_reason")

    # Restore the four single-column indexes.
    op.create_index("ix_scope_override_tenant_id", "scope_override", ["tenant_id"])
    op.create_index("ix_brief_tenant_id", "brief", ["tenant_id"])
    op.create_index("ix_prospect_identity_key", "prospect", ["identity_key"])
    op.create_index("ix_company_domain", "company", ["domain"])

    # Drop the composite list-sort indexes.
    op.drop_index("ix_company_tenant_fit", table_name="company")
    op.drop_index("ix_prospect_tenant_fit", table_name="prospect")

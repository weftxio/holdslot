"""scoring v2 — contraction: drop the retired v1 fit_* columns/indexes (V2-4)

Revision ID: 0026_scoring_v2_contraction
Revises: 0025_scoring_v2_rubrics
Create Date: 2026-07-10

The CONTRACT step of the scoring-v2 expand→cutover→contract (docs/initial-build-plan.md §D+.2, after
review #5 sign-off). The whole v1 0–100 scoring path — the sync twin endpoints, `fit.score` /
`score_company` / `collapse` / the market gate, and the feedback/batch/approval readers — was cut
over to the 4-label `label`/`score_total` verdict, so the v1 columns + their sort indexes are now
dead weight. This drops them.

Drops, on BOTH `company` and `prospect`:
  * `fit_score` INTEGER    — superseded by `score_total` (the 4–20 subscore sum).
  * `fit_tier`  VARCHAR(32) — superseded by `label` (the 4-label verdict).
  * the `ix_{company,prospect}_tenant_fit` composites (fit_score DESC) — the label-bucketed
    `ix_*_tenant_label` (from 0024) is the live list-feed index now.

Also on `prospect`:
  * DROP `outreach_outcome` VARCHAR(32) — never written or read anywhere (a Phase-C placeholder).
  * `status` server default `"new"` → `"found"` — `"new"` was never a live value (Apollo-found rows
    land `"found"`, manual adds `"found"` too); align the default with reality.

Reversible: downgrade re-adds the columns (nullable, EMPTY — the v1 data is not restored; it was
retired by design) + re-creates the two fit indexes + restores the old status default.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0026_scoring_v2_contraction"
down_revision: str | None = "0025_scoring_v2_rubrics"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Drop the v1 fit-score sort indexes first (the label-bucketed 0024 indexes serve the feed).
    op.drop_index("ix_company_tenant_fit", table_name="company")
    op.drop_index("ix_prospect_tenant_fit", table_name="prospect")

    # Drop the retired v1 verdict columns on both tables.
    op.drop_column("company", "fit_tier")
    op.drop_column("company", "fit_score")
    op.drop_column("prospect", "fit_tier")
    op.drop_column("prospect", "fit_score")

    # Prospect-only cleanups.
    op.drop_column("prospect", "outreach_outcome")
    op.alter_column("prospect", "status", server_default="found")


def downgrade() -> None:
    op.alter_column("prospect", "status", server_default="new")
    op.add_column("prospect", sa.Column("outreach_outcome", sa.String(32), nullable=True))

    op.add_column("prospect", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.add_column("prospect", sa.Column("fit_tier", sa.String(32), nullable=True))
    op.add_column("company", sa.Column("fit_score", sa.Integer(), nullable=True))
    op.add_column("company", sa.Column("fit_tier", sa.String(32), nullable=True))

    op.execute(
        "CREATE INDEX ix_prospect_tenant_fit ON prospect "
        "(tenant_id, fit_score DESC NULLS LAST, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_company_tenant_fit ON company "
        "(tenant_id, fit_score DESC NULLS LAST, created_at DESC)"
    )

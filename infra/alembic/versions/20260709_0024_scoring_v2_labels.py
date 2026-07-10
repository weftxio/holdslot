"""scoring v2 — 4-label contract columns on company + prospect (expand phase, no backfill)

Revision ID: 0024_scoring_v2_labels
Revises: 0023_brief_structure_v11
Create Date: 2026-07-09

D+ tiering v2 (docs/initial-build-plan.md §D+.2) replaces the 0–100 `AI Score` with a 4-label
system (`contact_now` / `contact_soon` / `low_fit` / `excluded_by_rules`). This is the EXPAND step
of an expand→cutover→contract cutover: it ADDS the v2 columns alongside the live v1 `fit_score` /
`fit_tier` (both stay until the contraction migration 0026, after UAT sign-off), so nothing the
current list feed reads is disturbed.

Adds, on BOTH `company` and `prospect`:
  * `label`       VARCHAR(32) NULL — the 4-label verdict; NULL = "needs re-score" (no backfill).
  * `score_total` INTEGER     NULL — the subscore sum 4–20 (spec §8); NULL until (re)scored.

(The spec's `verified` bool was dropped 2026-07-09 — founder call: it isn't meaningful, since the
web liveness call runs on every rescore so it would be true for almost every scored row. The web
liveness verdict itself still lives in `fit_components.liveness`.)

Index: a new `(tenant_id, label, score_total DESC NULLS LAST, created_at DESC)` composite on each
table — the label-bucketed list feed's read pattern (filter/group by label, best score first). The
v1 `ix_*_tenant_fit` composites are LEFT in place (the v1 feed still sorts by fit_score until the
cutover); 0026 drops them.

**No backfill** — `label`/`score_total` land NULL for every existing row (founder decision
2026-07-09: force a clean re-score rather than tier-map v1 scores, which would mislabel e.g. a
company in liquidation as `contact_soon`). Fully reversible: downgrade drops the two indexes and the
five columns.
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0024_scoring_v2_labels"
down_revision: str | None = "0023_brief_structure_v11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # v2 contract columns — additive, nullable (no backfill), alongside the live v1 fit_* columns.
    op.add_column("company", sa.Column("label", sa.String(32), nullable=True))
    op.add_column("company", sa.Column("score_total", sa.Integer(), nullable=True))
    op.add_column("prospect", sa.Column("label", sa.String(32), nullable=True))
    op.add_column("prospect", sa.Column("score_total", sa.Integer(), nullable=True))

    # Label-bucketed list-feed index (raw SQL for DESC NULLS LAST). The v1 ix_*_tenant_fit stays
    # until the contraction (0026); both coexist through the cutover.
    op.execute(
        "CREATE INDEX ix_company_tenant_label ON company "
        "(tenant_id, label, score_total DESC NULLS LAST, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_prospect_tenant_label ON prospect "
        "(tenant_id, label, score_total DESC NULLS LAST, created_at DESC)"
    )


def downgrade() -> None:
    op.drop_index("ix_prospect_tenant_label", table_name="prospect")
    op.drop_index("ix_company_tenant_label", table_name="company")
    op.drop_column("prospect", "score_total")
    op.drop_column("prospect", "label")
    op.drop_column("company", "score_total")
    op.drop_column("company", "label")

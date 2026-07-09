"""D+ Stage 1 — scope lineage + search-response telemetry on research_run

Revision ID: 0019_scope_lineage
Revises: 0018_brief_structure_v7
Create Date: 2026-07-08

Records what each Apollo find actually SENT and what came back, so the forward chain
(spec → find) is no longer a black box (D+ diagnosis #2 "flying blind"):

- `filter_body`  — the exact executed Apollo request body (override-proof lineage; a
  localStorage tuning or a relax level changes what was sent, and this captures it).
  find-people stores `{"per_org": {domain: {body, relax}}}`.
- `scope_source` — `ai` (spec block unchanged) · `custom` (operator override params) ·
  `lookalike` · NULL for non-Apollo runs.
- `result_meta`  — read off the SAME fetch response (no extra Apollo call): `total_entries`,
  `breadcrumbs` echo, `pages_fetched`, `relax_level`, filter-body `body_hash` (the page-cursor
  key, D+ Stage 3).

All three are nullable, no backfill — pre-existing runs read NULL. Additive, reversible.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0019_scope_lineage"
down_revision: str | None = "0018_brief_structure_v7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

JSONB = postgresql.JSONB


def upgrade() -> None:
    op.add_column("research_run", sa.Column("filter_body", JSONB, nullable=True))
    op.add_column("research_run", sa.Column("scope_source", sa.String(16), nullable=True))
    op.add_column("research_run", sa.Column("result_meta", JSONB, nullable=True))


def downgrade() -> None:
    op.drop_column("research_run", "result_meta")
    op.drop_column("research_run", "scope_source")
    op.drop_column("research_run", "filter_body")

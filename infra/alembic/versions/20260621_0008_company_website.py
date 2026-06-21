"""phase C (S2) — add company.website (click-through URL, distinct from the dedupe domain)

Revision ID: 0008_company_website
Revises: 0007_phase_c_companies
Create Date: 2026-06-21

The Step-1 list shows a clickable Website alongside the registrable Domain (the dedupe key).
`website` is the raw URL as sourced (may be a subdomain/path); nullable, no backfill.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0008_company_website"
down_revision: str | None = "0007_phase_c_companies"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("company", sa.Column("website", sa.String(512), nullable=True))


def downgrade() -> None:
    op.drop_column("company", "website")

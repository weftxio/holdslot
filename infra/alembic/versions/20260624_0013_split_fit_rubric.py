"""phase C — split the single fit rubric into company_fit + prospect_fit

Revision ID: 0013_split_fit_rubric
Revises: 0012_scope_override
Create Date: 2026-06-24

The fit rubric lived under one stage (`fit_scoring`) shared by both scoring doors — Step-1 company
buying-intent and Step-2 people reply-potential / decision-power. They now want independent system +
input prompts per stage, so this renames the existing rubric to `company_fit` and seeds a
`prospect_fit` rubric per tenant from the same latest body (the founder tunes the people rubric
separately from there). Append-only store, so the seed is the prospect rubric's v1. Up/down clean.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_split_fit_rubric"
down_revision: str | None = "0012_scope_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Rename the single rubric → the Step-1 company rubric.
    op.execute("UPDATE prompt SET stage = 'company_fit' WHERE stage = 'fit_scoring'")
    # Seed the Step-2 people rubric v1 from each tenant's latest company rubric body. ON CONFLICT
    # keeps it idempotent (re-run safe); a tenant with no rubric yet simply gets no seed.
    op.execute(
        """
        INSERT INTO prompt (tenant_id, stage, version, body)
        SELECT p.tenant_id, 'prospect_fit', 1, p.body
        FROM prompt p
        WHERE p.stage = 'company_fit'
          AND p.version = (
              SELECT MAX(p2.version) FROM prompt p2
              WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'company_fit'
          )
        ON CONFLICT (tenant_id, stage, version) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DELETE FROM prompt WHERE stage = 'prospect_fit'")
    op.execute("UPDATE prompt SET stage = 'fit_scoring' WHERE stage = 'company_fit'")

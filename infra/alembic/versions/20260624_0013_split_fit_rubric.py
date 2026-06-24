"""phase C — split the single fit rubric into company_fit + prospect_fit

Revision ID: 0013_split_fit_rubric
Revises: 0012_scope_override
Create Date: 2026-06-24

The fit rubric lived under one stage (`fit_scoring`) shared by both scoring doors — Step-1 company
buying-intent and Step-2 people reply-potential / decision-power. They now want independent system +
input prompts per stage, so this renames the existing rubric to `company_fit` and seeds a
`prospect_fit` rubric per tenant from the same latest body (the founder tunes the people rubric
separately from there). Append-only store, so the seed is the prospect rubric's v1.

**Up/down is fully LOSSLESS.** The split is a one-way semantic change — `company_fit` and
`prospect_fit` are intentionally different prompts, so there is no correct way to *merge* them back
into one stage. Rather than destroy the founder's `prospect_fit` edits on downgrade, the downgrade
**parks** them under an inert stage (`__prospect_fit_archived`) that the pre-0013 app never reads,
and the upgrade **restores** them before falling back to the seed. So a downgrade → re-upgrade
roundtrip preserves every `prospect_fit` version byte-for-byte; a fresh upgrade seeds v1 as before.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "0013_split_fit_rubric"
down_revision: str | None = "0012_scope_override"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Inert stage the pre-0013 app never queries; downgrade parks prospect_fit here, upgrade restores.
_ARCHIVED = "__prospect_fit_archived"


def upgrade() -> None:
    # Rename the single rubric → the Step-1 company rubric.
    op.execute("UPDATE prompt SET stage = 'company_fit' WHERE stage = 'fit_scoring'")
    # Restore any prospect_fit parked by a previous downgrade — this is what makes the roundtrip
    # lossless (a re-upgrade gets the founder's edits back verbatim, not a fresh re-seed).
    op.execute(f"UPDATE prompt SET stage = 'prospect_fit' WHERE stage = '{_ARCHIVED}'")
    # Seed the Step-2 people rubric v1 from each tenant's latest company rubric body — but ONLY
    # where no prospect_fit exists yet (a fresh install). ON CONFLICT DO NOTHING makes it idempotent
    # AND means the restore above always wins over a re-seed, so an edited rubric is never lost.
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
    # LOSSLESS reverse (see module docstring). Collapse company_fit back to the single `fit_scoring`
    # stage, and PARK prospect_fit under an inert stage instead of deleting it — the pre-0013 app
    # reads stage by exact match (`fit_scoring`), so the parked rows are invisible yet recoverable.
    # upgrade() restores them, so no founder edit is ever lost on a rollback.
    op.execute("UPDATE prompt SET stage = 'fit_scoring' WHERE stage = 'company_fit'")
    op.execute(f"UPDATE prompt SET stage = '{_ARCHIVED}' WHERE stage = 'prospect_fit'")

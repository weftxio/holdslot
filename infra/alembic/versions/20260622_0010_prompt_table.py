"""rename sourcing_doc → prompt (per-client prompt store, stage column) + seed briefing v1

`sourcing_doc` outgrew its name — it's the single home for every client-editable prompt, not just
sourcing. Rename the table to `prompt` and its `kind` discriminator to `stage`, remap the stored
values to clean stage names (`sourcing_prompt`→`sourcing`, `fit_rubric`→`fit_scoring`), and seed
`briefing` v1 (the Brief→ResearchSpec scoping prompt) so every prompt now lives in the DB per client
— the briefing prompt previously had no row (it was a code default + optional override).

Additive/rename only; no data loss. Idempotent seed (ON CONFLICT DO NOTHING).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0010_prompt_table"
down_revision = "0009_research_job"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_BRIEFING_SEED = Path(__file__).resolve().parents[3] / "docs" / "prompts" / "brief-structure-v5.md"


def _seed_briefing() -> None:
    """Seed `briefing` v1 from docs/prompts/ for the HoldSlot tenant (mirrors 0005's seed).

    Skipped if the tenant isn't present yet (out-of-order DB) or a v1 already exists — the founder
    can save v1 through the UI instead; the scoping worker falls back to the code default regardless.
    """
    bind = op.get_bind()
    tenant_id = bind.execute(
        sa.text("SELECT id FROM tenant WHERE slug = 'holdslot'")
    ).scalar_one_or_none()
    if tenant_id is None:
        return
    body = _BRIEFING_SEED.read_text(encoding="utf-8")
    bind.execute(
        sa.text(
            "INSERT INTO prompt (tenant_id, stage, version, body) "
            "VALUES (CAST(:tid AS uuid), 'briefing', 1, :body) "
            "ON CONFLICT (tenant_id, stage, version) DO NOTHING"
        ),
        {"tid": str(tenant_id), "body": body},
    )


def upgrade() -> None:
    op.rename_table("sourcing_doc", "prompt")
    op.alter_column("prompt", "kind", new_column_name="stage")
    op.execute("ALTER INDEX ix_sourcing_doc_tenant_id RENAME TO ix_prompt_tenant_id")
    op.execute(
        "ALTER TABLE prompt RENAME CONSTRAINT uq_sourcing_doc_tenant_kind_version "
        "TO uq_prompt_tenant_stage_version"
    )
    # Remap legacy doc-type values to clean stage names.
    op.execute("UPDATE prompt SET stage = 'sourcing' WHERE stage = 'sourcing_prompt'")
    op.execute("UPDATE prompt SET stage = 'fit_scoring' WHERE stage = 'fit_rubric'")
    _seed_briefing()


def downgrade() -> None:
    op.execute("DELETE FROM prompt WHERE stage = 'briefing'")
    op.execute("UPDATE prompt SET stage = 'fit_rubric' WHERE stage = 'fit_scoring'")
    op.execute("UPDATE prompt SET stage = 'sourcing_prompt' WHERE stage = 'sourcing'")
    op.execute(
        "ALTER TABLE prompt RENAME CONSTRAINT uq_prompt_tenant_stage_version "
        "TO uq_sourcing_doc_tenant_kind_version"
    )
    op.execute("ALTER INDEX ix_prompt_tenant_id RENAME TO ix_sourcing_doc_tenant_id")
    op.alter_column("prompt", "stage", new_column_name="kind")
    op.rename_table("prompt", "sourcing_doc")

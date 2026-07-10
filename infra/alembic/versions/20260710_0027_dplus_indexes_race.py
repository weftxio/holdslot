"""D+.5 fix wave — feed sort indexes, scoring-job race guard, research_run scan index, cleanup

Revision ID: 0027_dplus_indexes_race
Revises: 0026_scoring_v2_contraction
Create Date: 2026-07-10

The DB foundation for the D+.5 fix wave (docs/dplus-fix-plan.md, phase F1). Five index/constraint/data
changes that other phases build on:

  * R5  — the two list feeds sort `score_total DESC NULLS LAST, created_at DESC, id DESC`, but the only
    surviving composite (`ix_*_tenant_label`, from 0024) LEADS with `label`, so a label-agnostic feed
    page is a full tenant sort. Add the matching `(tenant_id, score_total DESC NULLS LAST,
    created_at DESC)` composite on BOTH `company` and `prospect`.
  * R9  — the "one in-flight job per (tenant, kind)" rule is check-then-insert with no DB backstop, so
    two concurrent POSTs both dispatch. Add a PARTIAL UNIQUE index on `scoring_job (tenant_id, kind)`
    WHERE status IN ('queued','running') — the second insert now raises IntegrityError, which
    `enqueue_scoring` catches and coalesces onto the winner.
  * R22 — `research_run` has no `(tenant_id, created_at)` index; the Stage-3 `_resume_page` scan and the
    find-history endpoint both table-scan. Add `(tenant_id, created_at DESC)`.
  * R29 — `ix_company_tenant_id` / `ix_prospect_tenant_id` are prefix-covered by the composites (incl.
    the new R5 ones) — dead write-amplification. Drop both. Also DELETE the retired `sourcing` prompt
    rows still lingering in `prompt`.

Reversible: downgrade drops the four new indexes, re-creates the two single-column indexes, and no-ops
the prompt delete (the retired rows are not restored — they were dead by design).
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0027_dplus_indexes_race"
down_revision: str | None = "0026_scoring_v2_contraction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # R5 — score-sorted feed composites (raw SQL for DESC NULLS LAST), matching the list-feed ORDER BY.
    op.execute(
        "CREATE INDEX ix_company_tenant_score ON company "
        "(tenant_id, score_total DESC NULLS LAST, created_at DESC)"
    )
    op.execute(
        "CREATE INDEX ix_prospect_tenant_score ON prospect "
        "(tenant_id, score_total DESC NULLS LAST, created_at DESC)"
    )

    # R9 — one-active-job-per-(tenant, kind) enforced in the DB (partial unique index).
    op.execute(
        "CREATE UNIQUE INDEX uq_scoring_job_active_tenant_kind ON scoring_job (tenant_id, kind) "
        "WHERE status IN ('queued', 'running')"
    )

    # R22a — research_run scan index (find-history + Stage-3 resume-page).
    op.execute(
        "CREATE INDEX ix_research_run_tenant_created ON research_run (tenant_id, created_at DESC)"
    )

    # R29a — drop the composite-covered single-column tenant indexes.
    op.drop_index("ix_company_tenant_id", table_name="company")
    op.drop_index("ix_prospect_tenant_id", table_name="prospect")

    # R29b — purge retired sourcing-stage prompt rows (Apollo-only teardown left them behind).
    op.execute("DELETE FROM prompt WHERE stage = 'sourcing'")


def downgrade() -> None:
    op.create_index("ix_prospect_tenant_id", "prospect", ["tenant_id"])
    op.create_index("ix_company_tenant_id", "company", ["tenant_id"])

    op.drop_index("ix_research_run_tenant_created", table_name="research_run")
    op.drop_index("uq_scoring_job_active_tenant_kind", table_name="scoring_job")
    op.drop_index("ix_prospect_tenant_score", table_name="prospect")
    op.drop_index("ix_company_tenant_score", table_name="company")
    # R29b is a data cleanup — the retired sourcing prompts are not restored (dead by design).

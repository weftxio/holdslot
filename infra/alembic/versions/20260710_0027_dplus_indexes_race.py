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

final-fix-plan additions (this file was unapplied when the plan landed, so edited in place):
  * N8  — `research_job` had the SAME check-then-insert race as `scoring_job` (a double Regenerate
    double-spends the DeepSeek Pro scoping call). Add a PARTIAL UNIQUE on `research_job (tenant_id)`
    WHERE status IN ('queued','running') — no `kind` column (one structuring surface per tenant), so
    the key is `tenant_id` alone. `enqueue_structuring` catches the IntegrityError and coalesces.
  * N48 — a CREATE UNIQUE aborts the whole upgrade if a dup active pair already exists. Terminal-ize
    (flip to `error`, keep the newest) any duplicate active rows on BOTH job tables BEFORE creating
    their partial-unique indexes.
  * N49 — `ix_research_run_tenant_id` is prefix-covered by the new R22a `(tenant_id, created_at DESC)`
    composite — dead write-amplification. Drop it too.

Reversible: downgrade drops the new indexes, re-creates the dropped single-column indexes, and no-ops
the prompt delete + the dup terminal-ization (data cleanups are not restored — they were dead/invalid).
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

    # N48 — a partial-unique CREATE aborts the whole upgrade if a duplicate active pair already
    # exists. Terminal-ize any duplicate active rows FIRST (keep the newest per key, flip the rest to
    # `error`), on BOTH job tables, so the two CREATE UNIQUE statements below can never fail.
    op.execute(
        "UPDATE scoring_job SET status = 'error', "
        "error = COALESCE(error, 'superseded: duplicate active job cleared for the 0027 unique') "
        "WHERE status IN ('queued', 'running') AND id NOT IN ("
        "  SELECT DISTINCT ON (tenant_id, kind) id FROM scoring_job "
        "  WHERE status IN ('queued', 'running') ORDER BY tenant_id, kind, created_at DESC)"
    )
    op.execute(
        "UPDATE research_job SET status = 'error', "
        "error = COALESCE(error, 'superseded: duplicate active job cleared for the 0027 unique') "
        "WHERE status IN ('queued', 'running') AND id NOT IN ("
        "  SELECT DISTINCT ON (tenant_id) id FROM research_job "
        "  WHERE status IN ('queued', 'running') ORDER BY tenant_id, created_at DESC)"
    )

    # R9 — one-active-job-per-(tenant, kind) enforced in the DB (partial unique index).
    op.execute(
        "CREATE UNIQUE INDEX uq_scoring_job_active_tenant_kind ON scoring_job (tenant_id, kind) "
        "WHERE status IN ('queued', 'running')"
    )

    # N8 — one-active-structuring-job-per-tenant enforced in the DB (partial unique; no kind column).
    op.execute(
        "CREATE UNIQUE INDEX uq_research_job_active_tenant ON research_job (tenant_id) "
        "WHERE status IN ('queued', 'running')"
    )

    # R22a — research_run scan index (find-history + Stage-3 resume-page).
    op.execute(
        "CREATE INDEX ix_research_run_tenant_created ON research_run (tenant_id, created_at DESC)"
    )

    # R29a — drop the composite-covered single-column tenant indexes.
    op.drop_index("ix_company_tenant_id", table_name="company")
    op.drop_index("ix_prospect_tenant_id", table_name="prospect")
    # N49 — research_run's tenant index is prefix-covered by the R22a composite created just above.
    op.drop_index("ix_research_run_tenant_id", table_name="research_run")

    # R29b — purge retired sourcing-stage prompt rows (Apollo-only teardown left them behind).
    op.execute("DELETE FROM prompt WHERE stage = 'sourcing'")


def downgrade() -> None:
    op.create_index("ix_research_run_tenant_id", "research_run", ["tenant_id"])  # N49
    op.create_index("ix_prospect_tenant_id", "prospect", ["tenant_id"])
    op.create_index("ix_company_tenant_id", "company", ["tenant_id"])

    op.drop_index("ix_research_run_tenant_created", table_name="research_run")
    op.drop_index("uq_research_job_active_tenant", table_name="research_job")  # N8
    op.drop_index("uq_scoring_job_active_tenant_kind", table_name="scoring_job")
    op.drop_index("ix_prospect_tenant_score", table_name="prospect")
    op.drop_index("ix_company_tenant_score", table_name="company")
    # R29b + N48 are data cleanups — the retired sourcing prompts and terminal-ized dup jobs are not
    # restored (dead / invalid by design).

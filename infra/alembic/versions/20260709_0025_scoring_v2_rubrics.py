"""scoring v2 — seed the company_score + prospect_score rubrics (new prompt stages)

Revision ID: 0025_scoring_v2_rubrics
Revises: 0024_scoring_v2_labels
Create Date: 2026-07-09

The v2 score calls (`company_score_v2` / `prospect_score_v2`, fit.py) read their axis-anchor rubric
from the `prompt` table, exactly as the v1 doors do — so a re-weighting stays a founder doc edit,
not a code change. This seeds v1 of TWO **new** stages, `company_score` and `prospect_score`, from
`docs/prompts/company-score-v1.md` + `prospect-score-v1.md`, one row per tenant.

The stages are deliberately NEW (not a version bump of `company_fit` / `prospect_fit`): the v1 fit
rubrics stay live + untouched through the expand→cutover→contract window, so a rollback still has a
working v1 scorer. The founder edits the v2 rubric from these new stages; V2-4's contraction retires
the v1 stages after UAT sign-off.

Seeds only tenants that already carry a `company_fit` prompt (a real, provisioned tenant), one
`version 1` row per new stage. Idempotent (`ON CONFLICT DO NOTHING`); a re-run or a down→up
roundtrip never duplicates or clobbers a later founder-edited version. Downgrade removes only the
pristine seed rows (body-exact match), leaving any post-seed edits intact.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision: str = "0025_scoring_v2_rubrics"
down_revision: str | None = "0024_scoring_v2_labels"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"
_SEEDS = (("company_score", "company-score-v1.md"), ("prospect_score", "prospect-score-v1.md"))
# Postgres trim() strips SPACES only — normalize whitespace both sides (the 0017/0023 lesson).
_WS = " \t\r\n"


def _body(filename: str) -> str:
    return (_PROMPTS / filename).read_text(encoding="utf-8").strip()


def upgrade() -> None:
    bind = op.get_bind()
    for stage, filename in _SEEDS:
        bind.execute(
            sa.text(
                """
                INSERT INTO prompt (tenant_id, stage, version, body)
                SELECT DISTINCT p.tenant_id, :stage, 1, :body
                FROM prompt p
                WHERE p.stage = 'company_fit'
                ON CONFLICT (tenant_id, stage, version) DO NOTHING
                """
            ),
            {"stage": stage, "body": _body(filename)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    for stage, filename in _SEEDS:
        bind.execute(
            sa.text("DELETE FROM prompt WHERE stage = :stage AND btrim(body, :ws) = :body"),
            {"stage": stage, "body": _body(filename), "ws": _WS},
        )

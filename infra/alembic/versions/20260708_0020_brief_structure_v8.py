"""spec v6 — re-seed the briefing prompt to brief-structure-v8 (person_titles / Query = rubric)

Revision ID: 0020_brief_structure_v8
Revises: 0019_scope_lineage
Create Date: 2026-07-08

D+ Stage 2 ("Query = rubric"): the people query now emits `person_titles` (the precise buying-role
wordings the fit rubric scores as its 14-pt title dimension) alongside the two native facets, and
the relax ladder queries titles first (strict→fuzzy) before falling back to seniority×department.
The briefing SYSTEM prompt must teach the model to emit titles (it previously forbade them). Same
mechanics as 0017/0018: the prompt store is append-only and `latest_system_prompt` overrides the
code default with the newest DB row, so this appends the v8 body as the NEXT `briefing` version —
but ONLY where the latest saved prompt equals a shipped default (v5, v6, or v7); founder-customized
prompts are never touched.

Data-only; no table changes. Idempotent; downgrade removes exactly the appended v8 rows.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0020_brief_structure_v8"
down_revision = "0019_scope_lineage"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"

# Postgres `trim()` strips SPACES only — normalize whitespace on both sides (the 0017 lesson).
_WS = " \t\r\n"


def upgrade() -> None:
    defaults = [
        (_PROMPTS / name).read_text(encoding="utf-8").strip()
        for name in ("brief-structure-v5.md", "brief-structure-v6.md", "brief-structure-v7.md")
    ]
    v8 = (_PROMPTS / "brief-structure-v8.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v8
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) IN (:d5, :d6, :d7)
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v8": v8, "d5": defaults[0], "d6": defaults[1], "d7": defaults[2], "ws": _WS},
    )


def downgrade() -> None:
    v8 = (_PROMPTS / "brief-structure-v8.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v8"),
        {"v8": v8, "ws": _WS},
    )

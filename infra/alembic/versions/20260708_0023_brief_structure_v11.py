"""re-seed the briefing prompt to brief-structure-v11 (D+ Stage 4: single keyword-feedback signal)

Revision ID: 0023_brief_structure_v11
Revises: 0022_brief_structure_v10
Create Date: 2026-07-08

v10 shipped BOTH `avoid_keywords[]` (a bare negative list) and `keyword_yield[]` (the per-keyword
win-rate scoreboard) into the payload — redundant, since the yield table is the outcome-grounded
superset (a 0%-yield keyword IS a negative, with magnitude). v11 drops `avoid_keywords` entirely and
folds its avoidance guidance into the KEYWORD YIELD block, so the model reads one keyword-feedback
signal instead of two. OUTPUT schema is unchanged (still spec v6); only the prompt changes. Same
mechanics as 0017/0018/0020/0021/0022: append the v11 body as the NEXT `briefing` version, but ONLY
where the latest saved prompt equals a shipped default (v5–v10); founder-customized prompts are
never touched.

Data-only; no table changes. Idempotent; downgrade removes exactly the appended v11 rows.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0023_brief_structure_v11"
down_revision = "0022_brief_structure_v10"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"

# Postgres `trim()` strips SPACES only — normalize whitespace on both sides (the 0017 lesson).
_WS = " \t\r\n"
_DEFAULTS = ("brief-structure-v5.md", "brief-structure-v6.md", "brief-structure-v7.md",
             "brief-structure-v8.md", "brief-structure-v9.md", "brief-structure-v10.md")


def upgrade() -> None:
    defaults = [(_PROMPTS / name).read_text(encoding="utf-8").strip() for name in _DEFAULTS]
    v11 = (_PROMPTS / "brief-structure-v11.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v11
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) IN (:d5, :d6, :d7, :d8, :d9, :d10)
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v11": v11, "d5": defaults[0], "d6": defaults[1], "d7": defaults[2], "d8": defaults[3],
         "d9": defaults[4], "d10": defaults[5], "ws": _WS},
    )


def downgrade() -> None:
    v11 = (_PROMPTS / "brief-structure-v11.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v11"),
        {"v11": v11, "ws": _WS},
    )

"""re-seed the briefing prompt to brief-structure-v9 (D+ Stage 3: avoid_keywords negative evidence)

Revision ID: 0021_brief_structure_v9
Revises: 0020_brief_structure_v8
Create Date: 2026-07-08

D+ Stage 3 recycles negative signal: the payload now carries `avoid_keywords[]` — descriptive
keywords that correlated with poor-fit / wrong-market rows in prior finds — and the briefing SYSTEM
prompt must teach the model to drop them from `q_organization_keyword_tags` / `q_keywords`. OUTPUT
schema is unchanged (still spec v6); only the prompt gains the instruction. Same mechanics as
0017/0018/0020: append the v9 body as the NEXT `briefing` version, but ONLY where the latest saved
prompt equals a shipped default (v5–v8); founder-customized prompts are never touched.

Data-only; no table changes. Idempotent; downgrade removes exactly the appended v9 rows.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0021_brief_structure_v9"
down_revision = "0020_brief_structure_v8"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"

# Postgres `trim()` strips SPACES only — normalize whitespace on both sides (the 0017 lesson).
_WS = " \t\r\n"
_DEFAULTS = ("brief-structure-v5.md", "brief-structure-v6.md", "brief-structure-v7.md",
             "brief-structure-v8.md")


def upgrade() -> None:
    defaults = [(_PROMPTS / name).read_text(encoding="utf-8").strip() for name in _DEFAULTS]
    v9 = (_PROMPTS / "brief-structure-v9.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v9
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) IN (:d5, :d6, :d7, :d8)
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v9": v9, "d5": defaults[0], "d6": defaults[1], "d7": defaults[2], "d8": defaults[3],
         "ws": _WS},
    )


def downgrade() -> None:
    v9 = (_PROMPTS / "brief-structure-v9.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v9"),
        {"v9": v9, "ws": _WS},
    )

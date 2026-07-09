"""re-seed the briefing prompt to brief-structure-v10 (D+ Stage 4: vocabulary grounding)

Revision ID: 0022_brief_structure_v10
Revises: 0021_brief_structure_v9
Create Date: 2026-07-08

D+ Stage 4 grounds the scope in outcome data + real customers: the payload now carries
`keyword_yield[]` (a per-keyword win-rate scoreboard) and `customer_anchors[]` (enriched paying-
customer firmographics), and the briefing SYSTEM prompt must teach the model to prefer high-yield
keywords / drop losers and to ground targeting in the anchors. The technology-UID filters are
server-resolved, so the prompt also tells the model NOT to emit them. OUTPUT schema is unchanged
(still spec v6); only the prompt changes. Same mechanics as 0017/0018/0020/0021: append the v10
body as the NEXT `briefing` version, but ONLY where the latest saved prompt equals a shipped default
(v5–v9); founder-customized prompts are never touched.

Data-only; no table changes. Idempotent; downgrade removes exactly the appended v10 rows.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0022_brief_structure_v10"
down_revision = "0021_brief_structure_v9"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"

# Postgres `trim()` strips SPACES only — normalize whitespace on both sides (the 0017 lesson).
_WS = " \t\r\n"
_DEFAULTS = ("brief-structure-v5.md", "brief-structure-v6.md", "brief-structure-v7.md",
             "brief-structure-v8.md", "brief-structure-v9.md")


def upgrade() -> None:
    defaults = [(_PROMPTS / name).read_text(encoding="utf-8").strip() for name in _DEFAULTS]
    v10 = (_PROMPTS / "brief-structure-v10.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v10
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) IN (:d5, :d6, :d7, :d8, :d9)
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v10": v10, "d5": defaults[0], "d6": defaults[1], "d7": defaults[2], "d8": defaults[3],
         "d9": defaults[4], "ws": _WS},
    )


def downgrade() -> None:
    v10 = (_PROMPTS / "brief-structure-v10.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v10"),
        {"v10": v10, "ws": _WS},
    )

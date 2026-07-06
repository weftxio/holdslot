"""spec v5 — re-seed the briefing prompt to brief-structure-v7 (no intent date windows)

Revision ID: 0018_brief_structure_v7
Revises: 0017_brief_structure_v6
Create Date: 2026-07-06

Founder verdict: the funding/jobs-posted date windows always over-constrained the company search,
so spec v5 removes them from the LLM contract; the briefing SYSTEM prompt must stop teaching them.
Same mechanics as 0017: the prompt store is append-only and `latest_system_prompt` overrides the
code default with the newest DB row, so this appends the v7 body as the NEXT `briefing` version —
but ONLY where the latest saved prompt equals a shipped default (v5 or v6); founder-customized
prompts are never touched.

Data-only; no table changes. Idempotent; downgrade removes exactly the appended v7 rows.
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0018_brief_structure_v7"
down_revision = "0017_brief_structure_v6"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"

# Postgres `trim()` strips SPACES only — normalize whitespace on both sides (the 0017 lesson).
_WS = " \t\r\n"


def upgrade() -> None:
    defaults = [
        (_PROMPTS / name).read_text(encoding="utf-8").strip()
        for name in ("brief-structure-v5.md", "brief-structure-v6.md")
    ]
    v7 = (_PROMPTS / "brief-structure-v7.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v7
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) IN (:d5, :d6)
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v7": v7, "d5": defaults[0], "d6": defaults[1], "ws": _WS},
    )


def downgrade() -> None:
    v7 = (_PROMPTS / "brief-structure-v7.md").read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v7"),
        {"v7": v7, "ws": _WS},
    )

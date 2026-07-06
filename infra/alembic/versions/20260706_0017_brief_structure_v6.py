"""multi-ICP scope — re-seed the briefing prompt to brief-structure-v6

Revision ID: 0017_brief_structure_v6
Revises: 0016_phase_d_batch_approval
Create Date: 2026-07-06

ResearchSpec v4 makes scoping per-ICP: the LLM now returns one `icp_targeting` entry per ICP
(strict json_schema), so the briefing SYSTEM prompt must instruct per-ICP output. The prompt store
is append-only and `latest_system_prompt` overrides the code default with the newest DB row — so
updating the code constant alone would silently keep running v5 wherever 0010 seeded it. This
appends the v6 body as the NEXT `briefing` version, but ONLY for tenants whose latest briefing
prompt still equals the shipped v5 default — a founder-customized prompt is never touched (the UI
badges it "custom" and its owner upgrades deliberately).

Data-only; no table changes. Idempotent: a tenant whose latest body already equals v6 is skipped.
Downgrade removes exactly the appended v6 rows (append-only reverse; custom edits untouched).
"""

from __future__ import annotations

from pathlib import Path

import sqlalchemy as sa
from alembic import op

revision = "0017_brief_structure_v6"
down_revision = "0016_phase_d_batch_approval"
branch_labels = None
depends_on = None

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"
_V5 = _PROMPTS / "brief-structure-v5.md"
_V6 = _PROMPTS / "brief-structure-v6.md"


# Postgres `trim()` strips SPACES only — a seed file's trailing newline would defeat the
# equality check — so both sides are whitespace-normalized: seed text Python-stripped, the
# stored body btrim'ed over the full whitespace set.
_WS = " \t\r\n"


def upgrade() -> None:
    v5 = _V5.read_text(encoding="utf-8").strip()
    v6 = _V6.read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO prompt (tenant_id, stage, version, body)
            SELECT p.tenant_id, 'briefing', p.version + 1, :v6
            FROM prompt p
            WHERE p.stage = 'briefing'
              AND p.version = (
                  SELECT MAX(p2.version) FROM prompt p2
                  WHERE p2.tenant_id = p.tenant_id AND p2.stage = 'briefing'
              )
              AND btrim(p.body, :ws) = :v5
            ON CONFLICT (tenant_id, stage, version) DO NOTHING
            """
        ),
        {"v5": v5, "v6": v6, "ws": _WS},
    )


def downgrade() -> None:
    v6 = _V6.read_text(encoding="utf-8").strip()
    op.get_bind().execute(
        sa.text("DELETE FROM prompt WHERE stage = 'briefing' AND btrim(body, :ws) = :v6"),
        {"v6": v6, "ws": _WS},
    )

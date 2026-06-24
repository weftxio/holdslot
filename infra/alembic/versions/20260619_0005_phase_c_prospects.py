"""phase C (S2) — prospects: prospect, research_run, sourcing_doc (+ seed v1 prompts)

Revision ID: 0005_phase_c
Revises: 0004_icp_suggestions
Create Date: 2026-06-19

The three MVP tables for the Apollo find→enrich loop. All tenant-scoped (the A4 guard
scopes them); `prospect` carries `identity_key` + `last_enriched_at` as the future `person`
enrich-once seam. Seeds `sourcing_doc` v1 of the fit rubric for HoldSlot tenant #0 from
`docs/prompts/*-v1.md`, so a fresh DB can run a round immediately.

`person`/`enrichment_request` (the SCALE enrich-once cache) are deliberately NOT built here.
"""

from collections.abc import Sequence
from pathlib import Path

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005_phase_c"
down_revision: str | None = "0004_icp_suggestions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_OBJ = sa.text("'{}'::jsonb")

# repo root: versions/ -> alembic/ -> infra/ -> root
_PROMPTS = Path(__file__).resolve().parents[3] / "docs" / "prompts"
# kind -> seed file (the data-schema `sourcing_doc.kind` values).
# The retired legacy `sourcing_prompt` seed was removed (the `sourcing` stage is dead under the
# Apollo-only rebuild); only the fit rubric is seeded. Fresh DBs no longer need the sourcing-prompt
# file.
SEED_DOCS = {
    "fit_rubric": "fit-scoring-rubric-v1.md",
}


def _tenant_fk() -> sa.ForeignKey:
    return sa.ForeignKey("tenant.id", ondelete="CASCADE")


def upgrade() -> None:
    op.create_table(
        "prospect",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("icp_id", UUID, sa.ForeignKey("icp.id", ondelete="SET NULL"), nullable=True),
        sa.Column("spec_version", sa.Integer, nullable=True),
        sa.Column("run_id", sa.String(64), nullable=True),
        sa.Column("identity_key", sa.String(255), nullable=False),
        sa.Column("enrichment", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("email_valid", sa.Boolean, nullable=False, server_default=sa.text("false")),
        sa.Column("fit_score", sa.Integer, nullable=True),
        sa.Column("fit_tier", sa.String(32), nullable=True),
        sa.Column("fit_components", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("source_lineage", JSONB, nullable=False, server_default=EMPTY_OBJ),
        sa.Column("status", sa.String(32), nullable=False, server_default="new"),
        sa.Column("outreach_outcome", sa.String(32), nullable=True),
        sa.Column("last_enriched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("tenant_id", "identity_key", name="uq_prospect_tenant_identity"),
    )
    op.create_index("ix_prospect_tenant_id", "prospect", ["tenant_id"])
    op.create_index("ix_prospect_identity_key", "prospect", ["identity_key"])

    op.create_table(
        "research_run",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("run_id", sa.String(64), nullable=False),
        sa.Column("spec_version", sa.Integer, nullable=True),
        sa.Column("icp_id", UUID, sa.ForeignKey("icp.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("prompt_version", sa.String(64), nullable=True),
        sa.Column("rubric_version", sa.String(64), nullable=True),
        sa.Column("rows_pushed", sa.Integer, nullable=False, server_default="0"),
        sa.Column("rows_accepted", sa.Integer, nullable=False, server_default="0"),
        sa.Column("cost_usd", sa.Numeric(14, 8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("run_id", name="uq_research_run_run_id"),
    )
    op.create_index("ix_research_run_tenant_id", "research_run", ["tenant_id"])

    op.create_table(
        "sourcing_doc",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("tenant_id", UUID, _tenant_fk(), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "tenant_id", "kind", "version", name="uq_sourcing_doc_tenant_kind_version"
        ),
    )
    op.create_index("ix_sourcing_doc_tenant_id", "sourcing_doc", ["tenant_id"])

    _seed_sourcing_docs()


def _seed_sourcing_docs() -> None:
    """Seed v1 of the fit rubric for HoldSlot tenant #0 from docs/prompts/.

    Idempotent (ON CONFLICT DO NOTHING on the unique (tenant, kind, version)). If the tenant
    isn't present yet (a DB seeded out of order) the seed is skipped — the founder can save v1
    through the UI instead; the round endpoint requires a fit rubric to exist anyway.
    """
    bind = op.get_bind()
    tenant_id = bind.execute(
        sa.text("SELECT id FROM tenant WHERE slug = 'holdslot'")
    ).scalar_one_or_none()
    if tenant_id is None:
        return
    for kind, filename in SEED_DOCS.items():
        body = (_PROMPTS / filename).read_text(encoding="utf-8")
        bind.execute(
            sa.text(
                "INSERT INTO sourcing_doc (tenant_id, kind, version, body) "
                "VALUES (CAST(:tid AS uuid), :kind, 1, :body) "
                "ON CONFLICT (tenant_id, kind, version) DO NOTHING"
            ),
            {"tid": str(tenant_id), "kind": kind, "body": body},
        )


def downgrade() -> None:
    op.drop_index("ix_sourcing_doc_tenant_id", table_name="sourcing_doc")
    op.drop_table("sourcing_doc")
    op.drop_index("ix_research_run_tenant_id", table_name="research_run")
    op.drop_table("research_run")
    op.drop_index("ix_prospect_identity_key", table_name="prospect")
    op.drop_index("ix_prospect_tenant_id", table_name="prospect")
    op.drop_table("prospect")

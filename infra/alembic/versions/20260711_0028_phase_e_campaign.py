"""Phase E (S4/S5) — campaign & outreach (campaign, message_variant, campaign_lead, outreach_event)

Revision ID: 0028_phase_e_campaign
Revises: 0027_dplus_indexes_race
Create Date: 2026-07-11

The outreach precondition (docs/initial-build-plan.md → Phase E): turn an *approved* `batch` into a
live Smartlead cold-email campaign and make the Campaign + Reply-queue funnel real. Four tables, one
EXPAND migration (migrate-first, deploy-first-safe — nothing the live product reads is touched):

  * `campaign`        — 1:1 with an approved batch (`batch_id` UNIQUE + FK RESTRICT: a campaign-bearing
                        batch becomes undeletable, closing the D delete-cascade hole). `status`
                        `draft`→`launching`→`sending`⇄`paused`→`completed`|`error`; `launching`
                        doubles as the async-launch job state (reaper semantics, no job table).
  * `message_variant` — A/B/C copy; `is_winner` a manual HoldSlot-side toggle. Open/reply rates are
                        DERIVED from `outreach_event`, never stored (the Phase-D derived-counts rule).
  * `campaign_lead`   — the funnel's single source of truth (`stage`). Inserted by the launch worker
                        only as each Smartlead lead-add succeeds. Carries `approval_id` — the billable
                        evidence hop `prospect_approval → campaign_lead → meeting` (FK RESTRICT).
  * `outreach_event`  — append-only ledger + reply-queue workflow. Webhook ingest is
                        `INSERT … ON CONFLICT (smartlead_event_id) DO NOTHING`; the dedupe IS the
                        PARTIAL-UNIQUE index `WHERE smartlead_event_id IS NOT NULL` (Smartlead
                        documents no unique event id — the key is the provider id if the E0 probe
                        found one, else a derived hash; either way the column + partial-unique are
                        unchanged). Raw SQL for the partial index (Alembic can't express it inline).

Same conventions as A–D: uuid PK, `tenant_id` CASCADE, timestamptz, string status (no DB enum), zero
new AWS resources. Fully reversible: downgrade drops the four tables + their indexes in FK order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0028_phase_e_campaign"
down_revision: str | None = "0027_dplus_indexes_race"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
EMPTY_JSON = sa.text("'{}'::jsonb")
FALSE = sa.text("false")


def _tenant_fk() -> sa.Column:
    fk = sa.ForeignKey("tenant.id", ondelete="CASCADE")
    return sa.Column("tenant_id", UUID, fk, nullable=False)


def upgrade() -> None:
    # campaign — 1:1 with an approved batch. batch_id UNIQUE + RESTRICT: undeletable while a campaign
    # references it (the D DELETE /batches/{id} CASCADE stops here — the billable chain can't orphan).
    op.create_table(
        "campaign",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "batch_id", UUID, sa.ForeignKey("batch.id", ondelete="RESTRICT"), nullable=False
        ),
        sa.Column("icp_id", UUID, sa.ForeignKey("icp.id", ondelete="SET NULL"), nullable=True),
        sa.Column("name", sa.String(255), nullable=False, server_default=""),
        sa.Column("smartlead_campaign_id", sa.String(64), nullable=True),
        # draft → launching → sending ⇄ paused → completed | error (launching = launch job state)
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("settings", JSONB, nullable=False, server_default=EMPTY_JSON),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("batch_id", name="uq_campaign_batch"),
        sa.UniqueConstraint(
            "tenant_id", "smartlead_campaign_id", name="uq_campaign_tenant_smartlead"
        ),
    )
    op.create_index(
        "ix_campaign_tenant_created", "campaign", ["tenant_id", sa.text("created_at DESC")]
    )

    # message_variant — A/B/C copy; metrics derived from outreach_event, never stored.
    op.create_table(
        "message_variant",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "campaign_id", UUID, sa.ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("key", sa.String(8), nullable=False),  # A / B / C
        sa.Column("subject", sa.String(255), nullable=False, server_default=""),
        sa.Column("body", sa.Text(), nullable=False, server_default=""),
        sa.Column("is_winner", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("campaign_id", "key", name="uq_message_variant_campaign_key"),
    )

    # campaign_lead — the funnel SoT. approval_id RESTRICT = the billable-evidence hop stays intact.
    op.create_table(
        "campaign_lead",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "campaign_id", UUID, sa.ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "prospect_id", UUID, sa.ForeignKey("prospect.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "approval_id",
            UUID,
            sa.ForeignKey("prospect_approval.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("smartlead_lead_id", sa.String(64), nullable=True),
        # contacted · followup · replied · meeting · noshow · billable · drop (funnel SoT)
        sa.Column("stage", sa.String(16), nullable=False, server_default="contacted"),
        sa.Column(
            "stage_changed_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW
        ),
        sa.Column("variant_key", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint(
            "campaign_id", "prospect_id", name="uq_campaign_lead_campaign_prospect"
        ),
    )
    op.create_index("ix_campaign_lead_tenant_id", "campaign_lead", ["tenant_id"])
    op.create_index(
        "ix_campaign_lead_campaign_stage", "campaign_lead", ["campaign_id", "stage"]
    )

    # outreach_event — append-only ledger + reply-queue workflow.
    op.create_table(
        "outreach_event",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "campaign_id", UUID, sa.ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "campaign_lead_id",
            UUID,
            sa.ForeignKey("campaign_lead.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("event_type", sa.String(32), nullable=False),
        sa.Column("smartlead_event_id", sa.String(128), nullable=True),
        sa.Column("payload", JSONB, nullable=False, server_default=EMPTY_JSON),
        sa.Column("triage", sa.String(32), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("response_body", sa.Text(), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    # The webhook idempotency key — PARTIAL unique (skip internal events, whose id is NULL). Raw SQL:
    # Alembic's create_index can't express the WHERE clause. This IS the dedupe (ON CONFLICT target).
    op.execute(
        "CREATE UNIQUE INDEX uq_outreach_event_smartlead_id ON outreach_event "
        "(smartlead_event_id) WHERE smartlead_event_id IS NOT NULL"
    )
    op.create_index(
        "ix_outreach_event_tenant_type_created",
        "outreach_event",
        ["tenant_id", "event_type", sa.text("created_at DESC")],
    )
    op.create_index("ix_outreach_event_campaign", "outreach_event", ["campaign_id"])
    op.create_index("ix_outreach_event_lead", "outreach_event", ["campaign_lead_id"])


def downgrade() -> None:
    op.drop_index("ix_outreach_event_lead", table_name="outreach_event")
    op.drop_index("ix_outreach_event_campaign", table_name="outreach_event")
    op.drop_index("ix_outreach_event_tenant_type_created", table_name="outreach_event")
    op.execute("DROP INDEX IF EXISTS uq_outreach_event_smartlead_id")
    op.drop_table("outreach_event")
    op.drop_index("ix_campaign_lead_campaign_stage", table_name="campaign_lead")
    op.drop_index("ix_campaign_lead_tenant_id", table_name="campaign_lead")
    op.drop_table("campaign_lead")
    op.drop_table("message_variant")
    op.drop_index("ix_campaign_tenant_created", table_name="campaign")
    op.drop_table("campaign")

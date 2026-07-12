"""Phase F (S6) — booking, meeting & feedback (booking_link, meeting, feedback_link)

Revision ID: 0030_phase_f_meeting
Revises: 0029_sending_account
Create Date: 2026-07-12

The booked-meeting precondition (docs/initial-build-plan.md → Phase F): turn a replied lead into a
tokenized booking link → a real Google Calendar/Meet event → a swept, qualified, billable `meeting`
row → post-meeting feedback. Three tables, one EXPAND migration (migrate-first, deploy-first-safe —
nothing the live product reads is touched):

  * `booking_link`  — tokenized expiring link, per replied lead. Mirrors `approval_link` (SHA-256
                      token_hash only, validity-on-read, atomic single-use `used_at`). `campaign_lead_id`
                      CASCADE + indexed so the resend ladder finds a lead's links.
  * `meeting`       — the one row feeding funnel · ledger · recaps. `approval_id` → `prospect_approval`
                      is the billing-evidence snapshot (RESTRICT / no-cascade: the qualify rule reads
                      this column, and the evidence can't be orphaned by a batch/campaign delete);
                      `campaign_lead_id`/`prospect_id` SET NULL (a manual, non-funnel meeting survives).
                      `billable` is DERIVED, never stored; feedback answers live on this row (1:1).
  * `feedback_link` — post-meeting feedback token; mirrors `booking_link`; `meeting_id` CASCADE.

Same conventions as A–E: uuid PK, `tenant_id` CASCADE, timestamptz, string status (no DB enum), zero
new AWS resources. Fully reversible: downgrade drops the three tables in FK order.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0030_phase_f_meeting"
down_revision: str | None = "0029_sending_account"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
JSONB = postgresql.JSONB
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")
FALSE = sa.text("false")
EMPTY_ARRAY = sa.text("'[]'::jsonb")


def _tenant_fk() -> sa.Column:
    fk = sa.ForeignKey("tenant.id", ondelete="CASCADE")
    return sa.Column("tenant_id", UUID, fk, nullable=False)


def upgrade() -> None:
    # booking_link — tokenized expiring link, per replied lead (mirror of approval_link).
    op.create_table(
        "booking_link",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "campaign_lead_id",
            UUID,
            sa.ForeignKey("campaign_lead.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_booking_link_campaign_lead_id", "booking_link", ["campaign_lead_id"])

    # meeting — the one row feeding funnel · ledger · recaps. approval_id RESTRICT (no cascade) = the
    # billing-evidence snapshot survives batch/campaign deletes; campaign_lead_id/prospect_id SET NULL.
    op.create_table(
        "meeting",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "campaign_lead_id",
            UUID,
            sa.ForeignKey("campaign_lead.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "prospect_id", UUID, sa.ForeignKey("prospect.id", ondelete="SET NULL"), nullable=True
        ),
        sa.Column(
            "approval_id",
            UUID,
            sa.ForeignKey("prospect_approval.id", ondelete="RESTRICT"),
            nullable=True,
        ),
        sa.Column("google_event_id", sa.String(128), nullable=True),
        sa.Column("meet_link", sa.String(255), nullable=True),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conference_record_id", sa.String(128), nullable=True),
        sa.Column("held", sa.Boolean(), nullable=True),
        sa.Column("duration_min", sa.Integer(), nullable=True),
        # qualified · short_call · noshow (derived once at ingest; later change = owner correction)
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("amount", sa.Numeric(10, 2), nullable=True),
        sa.Column("dispute_window_ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("disputed", sa.Boolean(), nullable=False, server_default=FALSE),
        sa.Column("feedback_rating", sa.Integer(), nullable=True),
        sa.Column("feedback_chips", JSONB, nullable=False, server_default=EMPTY_ARRAY),
        sa.Column("feedback_comment", sa.Text(), nullable=True),
        sa.Column("feedback_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("won", sa.Boolean(), nullable=True),
        sa.Column("summary", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index(
        "ix_meeting_tenant_scheduled", "meeting", ["tenant_id", sa.text("scheduled_at DESC")]
    )
    op.create_index("ix_meeting_campaign_lead_id", "meeting", ["campaign_lead_id"])

    # feedback_link — post-meeting feedback token (mirror of booking_link); meeting_id CASCADE.
    op.create_table(
        "feedback_link",
        sa.Column("id", UUID, primary_key=True, **PK),
        _tenant_fk(),
        sa.Column(
            "meeting_id", UUID, sa.ForeignKey("meeting.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_feedback_link_meeting_id", "feedback_link", ["meeting_id"])


def downgrade() -> None:
    op.drop_index("ix_feedback_link_meeting_id", table_name="feedback_link")
    op.drop_table("feedback_link")
    op.drop_index("ix_meeting_campaign_lead_id", table_name="meeting")
    op.drop_index("ix_meeting_tenant_scheduled", table_name="meeting")
    op.drop_table("meeting")
    op.drop_index("ix_booking_link_campaign_lead_id", table_name="booking_link")
    op.drop_table("booking_link")

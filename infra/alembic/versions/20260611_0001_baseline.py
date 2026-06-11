"""baseline — identity + tenancy core

Revision ID: 0001_baseline
Revises:
Create Date: 2026-06-11
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_baseline"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UUID = postgresql.UUID(as_uuid=True)
PK = dict(server_default=sa.text("gen_random_uuid()"))
NOW = sa.text("now()")

tenant_status = postgresql.ENUM("active", "suspended", name="tenant_status", create_type=False)
user_status = postgresql.ENUM("active", "disabled", name="user_status", create_type=False)
membership_role = postgresql.ENUM("owner", "member", name="membership_role", create_type=False)


def upgrade() -> None:
    bind = op.get_bind()
    tenant_status.create(bind, checkfirst=True)
    user_status.create(bind, checkfirst=True)
    membership_role.create(bind, checkfirst=True)

    op.create_table(
        "tenant",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("slug", sa.String(63), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("status", tenant_status, nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )

    op.create_table(
        "app_user",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("full_name", sa.String(255), nullable=True),
        sa.Column("status", user_status, nullable=False, server_default="active"),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )

    op.create_table(
        "membership",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "tenant_id",
            UUID,
            sa.ForeignKey("tenant.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("role", membership_role, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
    )
    op.create_index("ix_membership_tenant_id", "membership", ["tenant_id"])
    op.create_index("ix_membership_user_id", "membership", ["user_id"])

    op.create_table(
        "refresh_token",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_refresh_token_user_id", "refresh_token", ["user_id"])

    op.create_table(
        "password_reset",
        sa.Column("id", UUID, primary_key=True, **PK),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("app_user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=NOW),
    )
    op.create_index("ix_password_reset_user_id", "password_reset", ["user_id"])


def downgrade() -> None:
    op.drop_table("password_reset")
    op.drop_table("refresh_token")
    op.drop_index("ix_membership_user_id", table_name="membership")
    op.drop_index("ix_membership_tenant_id", table_name="membership")
    op.drop_table("membership")
    op.drop_table("app_user")
    op.drop_table("tenant")
    bind = op.get_bind()
    membership_role.drop(bind, checkfirst=True)
    user_status.drop(bind, checkfirst=True)
    tenant_status.drop(bind, checkfirst=True)

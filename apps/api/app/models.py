"""ORM models — the identity + tenancy core (A3).

Multi-tenant, role-aware by design, single-tenant in practice for the initial build:
`tenant` holds exactly HoldSlot (#0) today, but `membership` already carries `tenant_id`
+ `role`, so a paying client later is one INSERT, not a migration. Identity tables
(`app_user`, `refresh_token`, `password_reset`) are global — a person can belong to many
tenants via `membership`.

Email is stored normalized to lowercase by the app (a plain UNIQUE column) — no citext
extension needed.
"""

from __future__ import annotations

import enum
import uuid
from datetime import datetime

from sqlalchemy import (
    DateTime,
    Enum,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID as PgUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base


class MembershipRole(enum.StrEnum):
    owner = "owner"
    member = "member"


class TenantStatus(enum.StrEnum):
    active = "active"
    suspended = "suspended"


class UserStatus(enum.StrEnum):
    active = "active"
    disabled = "disabled"


def _uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(
        PgUUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Tenant(Base):
    __tablename__ = "tenant"

    id: Mapped[uuid.UUID] = _uuid_pk()
    slug: Mapped[str] = mapped_column(String(63), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[TenantStatus] = mapped_column(
        Enum(TenantStatus, name="tenant_status"),
        nullable=False,
        server_default=TenantStatus.active.value,
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="tenant", cascade="all, delete-orphan"
    )


class AppUser(Base):
    __tablename__ = "app_user"

    id: Mapped[uuid.UUID] = _uuid_pk()
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[UserStatus] = mapped_column(
        Enum(UserStatus, name="user_status"),
        nullable=False,
        server_default=UserStatus.active.value,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    memberships: Mapped[list[Membership]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )


class Membership(Base):
    __tablename__ = "membership"
    __table_args__ = (
        UniqueConstraint("user_id", "tenant_id", name="uq_membership_user_tenant"),
        Index("ix_membership_tenant_id", "tenant_id"),
        Index("ix_membership_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=False
    )
    role: Mapped[MembershipRole] = mapped_column(
        Enum(MembershipRole, name="membership_role"), nullable=False
    )
    created_at: Mapped[datetime] = _created_at()

    user: Mapped[AppUser] = relationship(back_populates="memberships")
    tenant: Mapped[Tenant] = relationship(back_populates="memberships")


class RefreshToken(Base):
    __tablename__ = "refresh_token"
    __table_args__ = (Index("ix_refresh_token_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class PasswordReset(Base):
    __tablename__ = "password_reset"
    __table_args__ = (Index("ix_password_reset_user_id", "user_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    user_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("app_user.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()

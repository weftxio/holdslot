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
    Integer,
    Numeric,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
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


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )


def _tenant_fk() -> Mapped[uuid.UUID]:
    """Every Phase-B business row is tenant-scoped — `tenant_id` is the spec's `client_id`."""
    return mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
    )


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
    # AI sourcing knob: how many passed-fit prospects anchor each round. Per-client config,
    # edited in the Sourcing-settings modal; a scalar (not a versioned SourcingDoc).
    seed_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("10"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
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
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
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
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    tenant_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("tenant.id", ondelete="CASCADE"),
        nullable=False,
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
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
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
        PgUUID(as_uuid=True),
        ForeignKey("app_user.id", ondelete="CASCADE"),
        nullable=False,
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


# ---------------------------------------------------------------------------
# Phase B (S1) — Targeting: Brief & ICP → research-ready ResearchSpec.
#
# Churn-proof by design (see docs/initial-build-plan.md → Phase B): Brief/ICP form
# fields live in opaque JSONB `data` documents — their only consumers are the form
# (round-trip) and the LLM prompt (schema-tolerant), so a form change is a frontend
# edit, never a migration. The `ResearchSpec` is the opposite — a locked v1 contract
# to Clay — stored append-only (versioned), each linked to the `LlmCall` that produced
# it. `LlmCall` is the one-seam telemetry every LLM feature writes through.
# ---------------------------------------------------------------------------


class Brief(Base):
    """One business brief per tenant. `data` is the opaque form document."""

    __tablename__ = "brief"
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_brief_tenant"),
        Index("ix_brief_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class Icp(Base):
    """Many ICP profiles per tenant. `name`/`tag` are the card header; `data` the form document."""

    __tablename__ = "icp"
    __table_args__ = (Index("ix_icp_tenant_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    tag: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class LlmCall(Base):
    """Append-only telemetry for every OpenRouter call — the one-seam observability row.

    Written by the B3 adapter on each call: served `model`, `prompt_version`, token
    counts, `cost_usd`, latency, `status` (ok|parse_error|timeout|error), retry count,
    and the `raw` completion JSON (the highest-value debugging signal). `status` is a
    plain string, not a DB enum, so new states never need a migration.
    """

    __tablename__ = "llm_call"
    __table_args__ = (
        Index("ix_llm_call_tenant_id", "tenant_id"),
        Index("ix_llm_call_purpose", "purpose"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    purpose: Mapped[str] = mapped_column(String(64), nullable=False)
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retries: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    raw: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ResearchSpec(Base):
    """Append-only, versioned LLM output — the locked v1 contract bridging Brief → Clay.

    A re-run never overwrites: it inserts the next `version` for the tenant. `spec` is
    the v1 targeting JSON (company_search/people_search/exclusions + server-merged credit
    policy); `gaps` are the value-loop prompts. `llm_call_id` ties the spec to the exact
    model/prompt/cost/raw output that produced it.
    """

    __tablename__ = "research_spec"
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_research_spec_tenant_version"),
        Index("ix_research_spec_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    spec: Mapped[dict] = mapped_column(JSONB, nullable=False)
    gaps: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    # Proposed ICPs inferred from the existing-customer list (alongside gaps, not in `spec`).
    icp_suggestions: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True),
        ForeignKey("llm_call.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[datetime] = _created_at()


# ---------------------------------------------------------------------------
# Phase C (S2) — Prospects: Clay seed + AI sourcing loop.
#
# The one boundary that drives everything (see docs/initial-build-plan.md → Phase C):
# **Clay is stateless enrichment compute; this DB is the only system of record.** Rows flow
# *through* Clay (push → enrich → pull → clear); tenant ownership, dedup, suppression, fit
# scoring, and lineage all live here. The MVP ships these three tenant-scoped tables; the
# `person`/`enrichment_request` enrich-once cache is the additive SCALE step (2nd tenant), not
# built. `identity_key` + `last_enriched_at` on `prospect` are that future `person` FK seam.
# ---------------------------------------------------------------------------


class Prospect(Base):
    """One targeting record per (identity × tenant) — enriched, fit-scored, lineage-tracked.

    `enrichment` holds the raw Clay/callback row (no S3 at MVP volume); `fit_components` holds
    the 12 rubric line-items + reason tags (the moat — three consumers, one structure). Re-import
    of the same `identity_key` for a tenant is idempotent (the unique constraint makes it an
    upsert), which is what makes a re-export safe to ingest twice.
    """

    __tablename__ = "prospect"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identity_key", name="uq_prospect_tenant_identity"),
        Index("ix_prospect_tenant_id", "tenant_id"),
        Index("ix_prospect_identity_key", "identity_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    enrichment: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    email_valid: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    fit_score: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fit_tier: Mapped[str | None] = mapped_column(String(32), nullable=True)
    fit_components: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # clay | ai_loop
    source_lineage: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="new")
    outreach_outcome: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class ResearchRun(Base):
    """One row per sourcing round or CSV import — the loop's scoreboard + Clay correlation handle.

    `run_id` is the value stamped on every Clay row pushed for this round and matched back on
    ingest. `rows_pushed`/`rows_accepted` + `cost_usd` (LLM spend) drive the per-source
    $/accepted scoreboard (C4); `prompt_version`/`rubric_version` tie a round to the exact
    `sourcing_doc` versions that produced it. Clay enrichment-credit cost is not recorded —
    Clay exposes no API for it (UI dashboard only), so the operator reconciles it manually.
    """

    __tablename__ = "research_run"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_research_run_run_id"),
        Index("ix_research_run_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # clay | ai_loop
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rows_pushed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_accepted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class SourcingDoc(Base):
    """Append-only founder-edited prompt/rubric — versioned data, never overwritten.

    Two kinds (`sourcing_prompt` | `fit_rubric`), each independently versioned per tenant. Seed
    v1 of both lands in the migration from `docs/prompts/*-v1.md`; the founder edits between
    rounds → a new (kind, version). A round records which versions it ran via `research_run`.
    """

    __tablename__ = "sourcing_doc"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "kind", "version", name="uq_sourcing_doc_tenant_kind_version"
        ),
        Index("ix_sourcing_doc_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)  # sourcing_prompt | fit_rubric
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()

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
    BigInteger,
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
# edit, never a migration. The `ResearchSpec` is the opposite — a versioned contract
# to Apollo — stored append-only, each linked to the `LlmCall` that produced
# it. `LlmCall` is the one-seam telemetry every LLM feature writes through.
# ---------------------------------------------------------------------------


class Brief(Base):
    """One business brief per tenant. `data` is the opaque form document."""

    __tablename__ = "brief"
    # uq_brief_tenant already creates a unique index on (tenant_id) — a separate ix_brief_tenant_id
    # would duplicate it, so it's dropped in migration 0014.
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_brief_tenant"),)

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
    """Append-only, versioned LLM output — the **v3** Apollo-native Brief→targeting contract.

    A re-run never overwrites: it inserts the next `version` for the tenant. `spec` is the v3
    targeting JSON (company_search_params · people_search_params · intent_filters · icp_validation +
    server-merged credit policy, all exact Apollo request fields); `gaps` + `icp_suggestions` are
    the value-loop signals stored alongside (never inside `spec`). `llm_call_id` ties the spec to
    the exact model/prompt/cost/raw output that produced it. `apollo_map` (Phase C) is the consumer.
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


class ResearchJob(Base):
    """Async structuring job — runs the Brief→ResearchSpec LLM call off the 30s API Gateway path.

    Scoping uses DeepSeek V4 Pro with thinking + web search (~55-76s), which exceeds the HTTP-API
    hard 30s cap. So `POST /brief/structure` inserts a `queued` row and fires a background worker
    (Lambda self async-invoke; a thread in local dev); the worker runs the LLM, inserts the next
    `ResearchSpec` version, and flips this row to `done` (recording `spec_version`) or `error`. The
    frontend polls `GET /brief/structure/status` until terminal — the sync POST returns fast (202).
    """

    __tablename__ = "research_job"
    __table_args__ = (
        Index("ix_research_job_tenant_id", "tenant_id"),
        # N8 (0027) — one in-flight structuring job per tenant, enforced in the DB so a concurrent
        # double-POST can't both dispatch the DeepSeek Pro scoping call. `enqueue_structuring`
        # catches the IntegrityError and coalesces. Partial: terminal rows don't participate.
        # No `kind` column (a tenant has one structuring surface), so the key is `tenant_id` alone.
        Index(
            "uq_research_job_active_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)  # set on done
    error: Mapped[str | None] = mapped_column(String, nullable=True)  # set on error
    llm_call_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("llm_call.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class ScoringJob(Base):
    """Async fit-scoring job — runs a scoring-bearing surface off the 30s API Gateway path (W4).

    The five scoring surfaces (find-company, find-lookalikes, company/prospect rescore, company
    field refresh) fan out one fit-scoring LLM call per row; a large batch exceeds the HTTP-API 30s
    cap, and the prior client-driven chunk loop dies if the browser tab closes. So the work moves to
    a background worker (Lambda self async-invoke; a thread in local dev): the kick-off endpoint
    inserts a `queued` row and the worker flips it `running`→`done`/`error`, recording per-run
    counts on `result`. `kind` names the surface; `params` is the original request body (ids,
    icp_id, …). One job per tenant×kind is in flight at a time so a re-click never double-spends.
    """

    __tablename__ = "scoring_job"
    __table_args__ = (
        Index("ix_scoring_job_tenant_kind", "tenant_id", "kind"),
        # D+.5 (0027, R9) — one in-flight job per (tenant, kind), enforced in the DB so a
        # concurrent double-POST can't both dispatch. `enqueue_scoring` catches the IntegrityError
        # and coalesces onto the winner. Partial: terminal (done/error) rows don't participate.
        Index(
            "uq_scoring_job_active_tenant_kind",
            "tenant_id",
            "kind",
            unique=True,
            postgresql_where=text("status IN ('queued', 'running')"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="queued")
    result: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    error: Mapped[str | None] = mapped_column(String, nullable=True)  # set on error
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


# ---------------------------------------------------------------------------
# Phase C (S2) — Prospects: Apollo find + enrich.
#
# The one boundary that drives everything (see docs/initial-build-plan.md → Phase C):
# **Apollo is headless discovery + enrichment compute; this DB is the only system of record.**
# Rows arrive from an Apollo REST call; tenant ownership, dedup, suppression, fit scoring, and
# lineage all live here. The MVP ships these three tenant-scoped tables; the
# `person`/`enrichment_request` enrich-once cache is the additive SCALE step (2nd tenant), not
# built. `identity_key` + `last_enriched_at` on `prospect` are that future `person` FK seam.
# (The legacy seed/CSV/AI-sourcing loop these tables originally served was removed in the
# Apollo-only teardown; `apollo_org_id`/`apollo_person_id` are added in C1's migration 0009.)
# ---------------------------------------------------------------------------


class Company(Base):
    """Stage-1 discovery row — one per (domain × tenant), fit-scored before any person is sourced.

    The company-first two-stage flow's system of record: Apollo **company search** lands these as
    `discovered`; the user selects (`selected`); **people search** then sources people *from the
    selected set* and links each `prospect.company_id` back by domain. Upsert of the same `domain`
    for a tenant is idempotent (the unique constraint), mirroring `prospect`'s `identity_key`
    dedupe. Scoring reuses the one door (`fit.py`) → the `label`/`score_total` verdict, persona
    lines omitted (company rubric). (The v1 `fit_score`/`fit_tier` cols were retired in 0026.)
    """

    __tablename__ = "company"
    __table_args__ = (
        UniqueConstraint("tenant_id", "domain", name="uq_company_tenant_domain"),
        UniqueConstraint("tenant_id", "apollo_org_id", name="uq_company_tenant_apollo_org"),
        # Scoring v2 (0024) — label-bucketed feed: filter/group by label, best score first. The v1
        # `ix_company_tenant_fit` (fit_score) was dropped in V2-4 (migration 0026).
        Index(
            "ix_company_tenant_label",
            "tenant_id",
            "label",
            text("score_total DESC NULLS LAST"),
            text("created_at DESC"),
        ),
        # D+.5 (0027) — the label-agnostic list feed sort (score best-first). The single-column
        # `ix_company_tenant_id` was dropped here — this composite prefix-covers it.
        Index(
            "ix_company_tenant_score",
            "tenant_id",
            text("score_total DESC NULLS LAST"),
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    # Apollo organization id — the Flow A→B scope link (passed as `organization_ids` to find
    # people). Nullable: a `manual` company has no Apollo id. Multiple NULLs are fine under the
    # unique constraint (Postgres), so manual adds never collide.
    apollo_org_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # The raw company URL as sourced (may differ from `domain`, e.g. a subdomain/path); `domain`
    # stays the registrable dedupe key, `website` is the click-through shown in the list.
    website: Mapped[str | None] = mapped_column(String(512), nullable=True)
    linkedin_url: Mapped[str | None] = mapped_column(String(512), nullable=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    industry: Mapped[str | None] = mapped_column(String(255), nullable=True)
    size: Mapped[str | None] = mapped_column(String(64), nullable=True)
    country: Mapped[str | None] = mapped_column(String(128), nullable=True)
    fit_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    fit_components: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Scoring v2 (0024, docs/initial-build-plan.md §D+.2) — the 4-label contract (the v1 fit_score/
    # fit_tier columns were retired in V2-4 / 0026). `label` NULL = "needs re-score" (no backfill);
    # `score_total` is the 4–20 subscore sum. Subscores/flags/reason/icp/liveness live in
    # `fit_components`; `fit_reason` = the v2 `reason`.
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # apollo | manual
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="discovered")
    created_at: Mapped[datetime] = _created_at()


class Prospect(Base):
    """One targeting record per (identity × tenant) — enriched, fit-scored, lineage-tracked.

    `enrichment` holds the raw Apollo enrichment row (no S3 at MVP volume); `fit_components` holds
    the 12 rubric line-items + reason tags (the moat — three consumers, one structure). Re-import
    of the same `identity_key` for a tenant is idempotent (the unique constraint makes it an
    upsert), which is what makes a re-export safe to ingest twice.
    """

    __tablename__ = "prospect"
    __table_args__ = (
        UniqueConstraint("tenant_id", "identity_key", name="uq_prospect_tenant_identity"),
        Index("ix_prospect_apollo_person_id", "tenant_id", "apollo_person_id"),
        # Scoring v2 (0024) — label-bucketed feed, mirrors company. The v1 `ix_prospect_tenant_fit`
        # (fit_score) was dropped in V2-4 (migration 0026).
        Index(
            "ix_prospect_tenant_label",
            "tenant_id",
            "label",
            text("score_total DESC NULLS LAST"),
            text("created_at DESC"),
        ),
        # D+.5 (0027) — the label-agnostic list feed sort (mirrors company). The single-column
        # `ix_prospect_tenant_id` was dropped here — this composite prefix-covers it.
        Index(
            "ix_prospect_tenant_score",
            "tenant_id",
            text("score_total DESC NULLS LAST"),
            text("created_at DESC"),
        ),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    # The stage-1 company this person belongs to (two-stage link; resolved by domain on import).
    company_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("company.id", ondelete="SET NULL"), nullable=True
    )
    spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    run_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    identity_key: Mapped[str] = mapped_column(String(255), nullable=False)
    # Apollo person id — the `people/match` enrich key. Nullable: a `manual` prospect has none.
    # Apollo-found rows also set `identity_key = "apollo:<id>"` (search exposes no
    # linkedin/email/domain pre-enrich, so this is the only stable dedupe key at find time).
    apollo_person_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    enrichment: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    email_valid: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    # Plain-text fit rationale — parity with company.fit_reason. Populated on the next rescore; the
    # structured per-line detail still lives in fit_components. (The v1 fit_score/fit_tier columns
    # were retired in V2-4 / migration 0026 — the verdict is `label`/`score_total` below.)
    fit_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    fit_components: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    # Scoring v2 (0024) — the 4-label contract for people (spec people-tier; company label caps the
    # person). `label` NULL = needs re-score; `score_total` is the 4–20 sum. subscores/flags/reason/
    # icp live in `fit_components`.
    label: Mapped[str | None] = mapped_column(String(32), nullable=True)
    score_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # apollo | manual
    source_lineage: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="found")
    last_enriched_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = _created_at()


class ResearchRun(Base):
    """One row per research run — the scoreboard + run correlation handle (source="apollo").

    `run_id` correlates every row sourced in this round (stamped on each `company`/`prospect`).
    `rows_pushed`/`rows_accepted` + `cost_usd` (LLM spend) drive the per-source $/accepted
    scoreboard (C4); `prompt_version`/`rubric_version` tie a round to the exact `prompt` versions
    that produced it. Apollo credit-spend is recorded separately at the enrich gate (C5), not here.
    """

    __tablename__ = "research_run"
    __table_args__ = (
        UniqueConstraint("run_id", name="uq_research_run_run_id"),
        # D+.5 (0027, R22a) — the Stage-3 `_resume_page` scan + find-history endpoint sort by
        # (tenant, created_at DESC); without this they table-scan. Its `tenant_id` prefix covers
        # plain tenant lookups, so the old single-column `ix_research_run_tenant_id` was dropped as
        # dead write-amplification (N49).
        Index("ix_research_run_tenant_created", "tenant_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    run_id: Mapped[str] = mapped_column(String(64), nullable=False)
    spec_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    source: Mapped[str] = mapped_column(String(32), nullable=False)  # apollo | manual
    prompt_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rubric_version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rows_pushed: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    rows_accepted: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    cost_usd: Mapped[float | None] = mapped_column(Numeric(14, 8), nullable=True)
    # D+ Stage 1 (0019) — scope lineage + search-response telemetry, all nullable / no backfill.
    # filter_body = exact executed Apollo body · scope_source = ai|custom|lookalike ·
    # result_meta = total_entries / breadcrumbs / pages_fetched / relax_level / body_hash.
    filter_body: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    scope_source: Mapped[str | None] = mapped_column(String(16), nullable=True)
    result_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Prompt(Base):
    """Append-only per-client prompt store — versioned text, never overwritten.

    One row per (tenant, `stage`, version); the latest version is active. `stage` is the
    pipeline step the prompt drives: `briefing` (Brief→ResearchSpec scoping), `sourcing` (legacy,
    retired), `company_fit` + `prospect_fit` (the two fit rubrics — Step-1 company buying-intent and
    Step-2 people reply-potential/decision-power, split from the original single fit rubric in
    migration 0013). Seed v1 of each lands in a migration from `docs/prompts/*.md`; the founder
    edits it → a new (stage, version). `research_run` records which rubric version it scored
    against.
    (Renamed from `sourcing_doc`/`kind` once it grew past sourcing into the single home for every
    client-editable prompt.)
    """

    __tablename__ = "prompt"
    __table_args__ = (
        UniqueConstraint("tenant_id", "stage", "version", name="uq_prompt_tenant_stage_version"),
        Index("ix_prompt_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    stage: Mapped[str] = mapped_column(String(32), nullable=False)  # see docstring for stage names
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    body: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[datetime] = _created_at()


class ScopeOverride(Base):
    """One live manual scope override per (tenant, `kind`) — the Find Settings modal saved to the
    server so it persists across browsers/devices (replaces the old per-browser localStorage).

    `kind` is the pipeline step the override tunes: `people` (Step-2 Find People facets) today;
    `company` (Step-1 sourcing) can reuse this row shape later with no migration. `params` is the
    opaque override payload merged over the AI `research_spec` at find time — deleting the row
    reverts to the AI scope. Single-row UPSERT, not versioned: the `research_spec` is the audit
    trail; this is just the current tuning the operator last saved."""

    __tablename__ = "scope_override"
    # uq_scope_override_tenant_kind (tenant_id, kind) covers tenant_id lookups via its leftmost
    # prefix, so a separate ix_scope_override_tenant_id is redundant — dropped in migration 0014.
    __table_args__ = (UniqueConstraint("tenant_id", "kind", name="uq_scope_override_tenant_kind"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    kind: Mapped[str] = mapped_column(String(16), nullable=False)  # people · company
    params: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


# ---------------------------------------------------------------------------
# Phase D (S3) — Sendout Batch + Client Approval: the revenue precondition.
#
# The one idea that drives everything (see docs/initial-build-plan.md → Phase D):
# **the approved prospect is the billable agreement; the client never sees clear-text contact
# data.** Enriched Phase-C prospects are grouped into a `batch`; the client gets a tokenized,
# expiring, MASKED approval link (the `approval_link`, an opaque-hash token mirroring
# `password_reset` — expiry checked on read, no scheduler); each per-prospect decision is the
# append-only `prospect_approval` row S7 bills against. `approval_template` is the thin per-tenant
# sendout copy override (mirrors `brief`). Counts (total/approved) are DERIVED from
# `prospect_approval`, never stored — deriving avoids drift. Reuses A/B/C primitives wholesale:
# NO EventBridge, NO async worker, NO new AWS resources.
# ---------------------------------------------------------------------------


class Batch(Base):
    """One sendout batch per group of enriched prospects — the unit the client approves.

    `status` walks `draft` → `sent` → `approved` | `changes_requested` (plain string, not a DB
    enum, so a new state never needs a migration). Total/approved counts are **derived** from the
    child `prospect_approval` rows (deriving avoids the dual-write drift a stored counter invites),
    so this row holds only the batch's identity + lifecycle timestamps.
    """

    __tablename__ = "batch"
    # List feed orders by (tenant, created_at desc) — the composite matches that ORDER BY exactly.
    __table_args__ = (Index("ix_batch_tenant_created", "tenant_id", text("created_at DESC")),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ProspectApproval(Base):
    """⭐ The billable record — one append-only row per (prospect × batch), carrying the decision.

    `decision` walks `pending` → `approved` | `removed` (`request_changes` is a batch-level state
    on `batch.status`, not a per-prospect value). **Append-only**: "removed" is a decision value,
    never a delete — the row is the audit/billing evidence S7's qualified-meeting rule charges on.
    `unique(batch_id, prospect_id)` makes "add the same prospect to the batch twice" idempotent.
    """

    __tablename__ = "prospect_approval"
    # uq_prospect_approval_batch_prospect (batch_id, prospect_id) covers batch_id lookups via its
    # leftmost prefix (the derived-count rollups GROUP BY batch_id), so no separate batch_id index.
    __table_args__ = (
        UniqueConstraint("batch_id", "prospect_id", name="uq_prospect_approval_batch_prospect"),
        Index("ix_prospect_approval_tenant_id", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("batch.id", ondelete="CASCADE"), nullable=False
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("prospect.id", ondelete="CASCADE"), nullable=False
    )
    decision: Mapped[str] = mapped_column(String(32), nullable=False, server_default="pending")
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ApprovalLink(Base):
    """The tokenized, expiring approval link — mirrors `password_reset` exactly.

    The raw `secrets.token_urlsafe` token lives only in the emailed URL; the DB stores its SHA-256
    `token_hash` (unique). Validity is checked **on read** (`expires_at` + single-use `used_at`) —
    no scheduler. The resend ladder mints a fresh row each send (we store only the hash, so the raw
    token can't be re-emailed); double-decide is prevented downstream by gating validity on
    `batch.status == sent`, not by token reuse. `batch_id` is indexed to find a batch's links.
    """

    __tablename__ = "approval_link"
    __table_args__ = (Index("ix_approval_link_batch_id", "batch_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("batch.id", ondelete="CASCADE"), nullable=False
    )
    recipient_email: Mapped[str] = mapped_column(String(320), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class ApprovalTemplate(Base):
    """One sendout-copy override per tenant (mirrors `brief`) — the thinnest slice.

    `data` is the opaque `{subject, body, cta}` doc (with `{{client_name}}`/`{{count}}` tokens); a
    code default serves until the founder edits it, so the row need not exist for a send to work.
    """

    __tablename__ = "approval_template"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_approval_template_tenant"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


# ============================================================ Phase E (S4/S5) — campaign & outreach
# (migration 0028). Statuses/stages are plain strings (never DB enums); counts/metrics are DERIVED
# from `outreach_event`, never stored (the Phase-D rule). `campaign_lead.stage` is the funnel's
# single source of truth; Smartlead webhook events are inputs to it. Behavior spec →
# docs/initial-build-plan.md § Phase E; schema → docs/data-schema.md § Phase E.


class Campaign(Base):
    """One outreach campaign per approved batch — the Smartlead campaign HoldSlot owns the state of.

    `status` walks `draft` → `launching` → `sending` ⇄ `paused` → `completed` | `error` (plain
    string). **`launching` doubles as the async-launch job state** — a stale `launching` older than
    `MAX_JOB_AGE_SECONDS` flips `error` on read (the `scoring_job` reaper semantics, no separate job
    table). `batch_id` is unique + RESTRICT, so a campaign-bearing batch is undeletable (the D
    `DELETE /batches/{id}` cascade stops here — the billable-evidence chain can't be orphaned).
    """

    __tablename__ = "campaign"
    __table_args__ = (
        UniqueConstraint("batch_id", name="uq_campaign_batch"),
        UniqueConstraint("tenant_id", "smartlead_campaign_id", name="uq_campaign_tenant_smartlead"),
        Index("ix_campaign_tenant_created", "tenant_id", text("created_at DESC")),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    batch_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("batch.id", ondelete="RESTRICT"), nullable=False
    )
    icp_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("icp.id", ondelete="SET NULL"), nullable=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    smartlead_campaign_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, server_default="draft")
    settings: Mapped[dict] = mapped_column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class MessageVariant(Base):
    """A/B/C outreach copy per campaign. Open/reply rates are DERIVED from `outreach_event`, never
    stored (same rule as batch counts). `is_winner` is a manual HoldSlot-side toggle (E6) — the
    Smartlead sequences lock while ACTIVE, so it never writes back."""

    __tablename__ = "message_variant"
    __table_args__ = (
        UniqueConstraint("campaign_id", "key", name="uq_message_variant_campaign_key"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    key: Mapped[str] = mapped_column(String(8), nullable=False)  # A / B / C
    subject: Mapped[str] = mapped_column(String(255), nullable=False, server_default="")
    body: Mapped[str] = mapped_column(String, nullable=False, server_default="")
    is_winner: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class CampaignLead(Base):
    """The funnel's single source of truth — one row per (campaign × prospect).

    Rows are inserted by the launch worker **only as each Smartlead lead-add succeeds** (stage
    `contacted`), so the funnel never shows a lead that wasn't actually pushed; re-launch resumes
    idempotently on the missing rows. `stage` moves only through the server allowed-moves map
    (mirror of the FE `MOVES` table; illegal = 409) and every move also writes a `stage_moved`
    event. `approval_id` is the billable-evidence hop `prospect_approval → campaign_lead → meeting`;
    RESTRICT keeps the approval row undeletable while referenced.
    """

    __tablename__ = "campaign_lead"
    __table_args__ = (
        UniqueConstraint("campaign_id", "prospect_id", name="uq_campaign_lead_campaign_prospect"),
        Index("ix_campaign_lead_tenant_id", "tenant_id"),
        Index("ix_campaign_lead_campaign_stage", "campaign_id", "stage"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    prospect_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("prospect.id", ondelete="CASCADE"), nullable=False
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("prospect_approval.id", ondelete="RESTRICT"), nullable=True
    )
    smartlead_lead_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stage: Mapped[str] = mapped_column(String(16), nullable=False, server_default="contacted")
    stage_changed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    variant_key: Mapped[str | None] = mapped_column(String(8), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class OutreachEvent(Base):
    """Append-only outreach ledger + the reply-queue workflow — the single source for the per-lead
    timeline, the variant scoreboard, and the Reply queue.

    Webhook ingest is `INSERT … ON CONFLICT (smartlead_event_id) DO NOTHING` — the dedupe **is** the
    partial-unique index (created in 0028; `WHERE smartlead_event_id IS NOT NULL`). The key is the
    provider event id if the E0 probe found one, else a derived hash (see `service.dedupe_key`).
    """

    __tablename__ = "outreach_event"
    __table_args__ = (
        Index(
            "ix_outreach_event_tenant_type_created",
            "tenant_id",
            "event_type",
            text("created_at DESC"),
        ),
        Index("ix_outreach_event_campaign", "campaign_id"),
        Index("ix_outreach_event_lead", "campaign_lead_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign.id", ondelete="CASCADE"), nullable=False
    )
    campaign_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign_lead.id", ondelete="SET NULL"), nullable=True
    )
    event_type: Mapped[str] = mapped_column(String(32), nullable=False)
    smartlead_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    triage: Mapped[str | None] = mapped_column(String(32), nullable=True)
    handled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    response_body: Mapped[str | None] = mapped_column(String, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    created_at: Mapped[datetime] = _created_at()


class SendingAccount(Base):
    """A warmed Smartlead sending inbox owned by one tenant — the per-tenant replacement for the
    secret's global `sending_account_ids`. The launch worker attaches this tenant's `active` inboxes
    to its Smartlead campaign (`add_email_accounts`).

    Lives in the DB, NOT Secrets Manager: an inbox id is a reference, not a credential (the shared
    Smartlead `api_key` is the one secret), and the tenant→inbox mapping is tenant-scoped config
    that grows per client — a row per onboarding, not a global-secret edit + cache-bust + redeploy.
    An inbox should back exactly one tenant's pool (`UNIQUE(tenant_id, smartlead_account_id)` is
    per-tenant; a soft cross-tenant guard can come with multi-client). `status`:
    warming|active|paused — only `active` inboxes send.
    """

    __tablename__ = "sending_account"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "smartlead_account_id", name="uq_sending_account_tenant_smartlead"
        ),
        Index("ix_sending_account_tenant", "tenant_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    smartlead_account_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    from_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    from_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


# ==================================================== Phase F (S6) — booking, meeting & feedback
# (migration 0030). `booking_link`/`feedback_link` mirror `approval_link` exactly (SHA-256
# token_hash only; validity-on-read; atomic single-use `used_at` claim). `meeting` is the one row
# feeding funnel · ledger · recaps; feedback answers live ON it (1:1, no feedback table). `billable`
# is NEVER stored — derived as `outcome=='qualified' AND amount IS NOT NULL AND
# dispute_window_ends_at
# < now() AND NOT disputed`; `amount` ($500 = PER_MEETING_USD) is stamped only when `approval_id` is
# present (no approval evidence → never billable). Behavior spec → docs/initial-build-plan.md §
# Phase F; schema → docs/data-schema.md § Phase F.


class BookingLink(Base):
    """The tokenized, expiring booking link, per replied lead — mirrors `approval_link` exactly.

    The raw `secrets.token_urlsafe` token lives only in the sent reply; the DB stores its SHA-256
    `token_hash` (unique). Validity is checked **on read** (`expires_at` + single-use `used_at`,
    7-day TTL) — no scheduler. `POST /book/{token}` claims `used_at` atomically (the double-book
    guard). The resend ladder revokes a lead's prior live links and mints a fresh row;
    `campaign_lead_id` is indexed so that ladder can find them.
    """

    __tablename__ = "booking_link"
    __table_args__ = (Index("ix_booking_link_campaign_lead_id", "campaign_lead_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    campaign_lead_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign_lead.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class Subscription(Base):
    """Phase G (S7, migration `0031`) — one billing row per PAYING tenant; tenant #0 (dogfood) has
    none, so its billing stays computed-only. Carries the Stripe customer/subscription handles, the
    plan-derived enrichment/ICP caps + the month usage counter (the GS4 enrich-cap guard), and the
    Stripe-mirrored `status`. `amount`/`is_billable` on `meeting` are unchanged — GS only adds the
    charge trigger (`meeting.billed_at`) + this state. Ships DORMANT (no rows until FR-7/FR-8)."""

    __tablename__ = "subscription"
    __table_args__ = (UniqueConstraint("tenant_id", name="uq_subscription_tenant"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    plan: Mapped[str] = mapped_column(String(16), nullable=False, server_default="free")
    stripe_customer_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    stripe_subscription_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    activation_paid_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    enrichment_cap: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    icp_limit: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    current_month_usage: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    usage_month: Mapped[str | None] = mapped_column(String(7), nullable=True)  # YYYY-MM (UTC)
    admin_quota_override: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overage_enabled: Mapped[bool] = mapped_column(nullable=False, server_default=text("true"))
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class BillingEvent(Base):
    """Phase G (`0031`) — append-only Stripe webhook log + the idempotency store (GS5). Mirrors the
    `outreach_event` posture: the raw verified event is stored deduped on `stripe_event_id` (the
    unique key), so a Stripe retry is a no-op. `tenant_id` resolves off the customer id (NULL if
    unknown, still stored). Ships dormant with the rest of GS."""

    __tablename__ = "billing_event"
    __table_args__ = (Index("ix_billing_event_tenant_id", "tenant_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("tenant.id", ondelete="CASCADE"), nullable=True
    )
    stripe_event_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    type: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default=text("'{}'::jsonb"))
    created_at: Mapped[datetime] = _created_at()


class Meeting(Base):
    """The one meeting row — funnel · ledger · recaps all derive from it; the public booking claim
    is the ONLY writer (a bare `replied→meeting` console move creates no row, FD-4).

    `approval_id` is the billing-evidence **snapshot** taken off `campaign_lead.approval_id` at
    booking time (no cascade / RESTRICT — the qualify rule reads this column, not a live join).
    `held` is NULL until the on-read sweep ingests it (the `WHERE held IS NULL` claim guard): true =
    a Meet conference record with ≥2 participants (FD-2); false = no-show, decided only past a 24h
    grace (FD-3). `amount` ($500) + `dispute_window_ends_at` (record end+48h) stamped only when
    the meeting `qualified` AND `approval_id` is present. Feedback lands on this row (1:1).
    """

    __tablename__ = "meeting"
    __table_args__ = (
        Index("ix_meeting_tenant_scheduled", "tenant_id", text("scheduled_at DESC")),
        Index("ix_meeting_campaign_lead_id", "campaign_lead_id"),
    )

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    campaign_lead_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("campaign_lead.id", ondelete="SET NULL"), nullable=True
    )
    prospect_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("prospect.id", ondelete="SET NULL"), nullable=True
    )
    approval_id: Mapped[uuid.UUID | None] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("prospect_approval.id", ondelete="RESTRICT"), nullable=True
    )
    google_event_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    meet_link: Mapped[str | None] = mapped_column(String(255), nullable=True)
    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conference_record_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    held: Mapped[bool | None] = mapped_column(nullable=True)
    duration_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    outcome: Mapped[str | None] = mapped_column(String(16), nullable=True)
    amount: Mapped[float | None] = mapped_column(Numeric(10, 2), nullable=True)
    dispute_window_ends_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    disputed: Mapped[bool] = mapped_column(nullable=False, server_default=text("false"))
    feedback_rating: Mapped[int | None] = mapped_column(Integer, nullable=True)
    feedback_chips: Mapped[list] = mapped_column(
        JSONB, nullable=False, server_default=text("'[]'::jsonb")
    )
    feedback_comment: Mapped[str | None] = mapped_column(String, nullable=True)
    feedback_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    won: Mapped[bool | None] = mapped_column(nullable=True)
    summary: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    # GS3 (`0031`) — the charge-emitted stamp: set once the billing sweep emits this meeting's meter
    # event (idempotent `WHERE billed_at IS NULL` claim). NULL for every meeting until Stripe goes
    # live; `is_billable`/`billing_chip` are unchanged (billing stays derived on read).
    billed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class FeedbackLink(Base):
    """The tokenized, expiring post-meeting feedback link — mirrors `booking_link`/`approval_link`.

    SHA-256 `token_hash` only; validity-on-read (7-day TTL); atomic single-use claim on submit. The
    public `POST /feedback/{token}` writes `feedback_rating/chips/comment/feedback_at` onto the
    referenced `meeting` (1:1). `meeting_id` is indexed (CASCADE — links die with their meeting).
    """

    __tablename__ = "feedback_link"
    __table_args__ = (Index("ix_feedback_link_meeting_id", "meeting_id"),)

    id: Mapped[uuid.UUID] = _uuid_pk()
    tenant_id: Mapped[uuid.UUID] = _tenant_fk()
    meeting_id: Mapped[uuid.UUID] = mapped_column(
        PgUUID(as_uuid=True), ForeignKey("meeting.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()

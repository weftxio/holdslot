"""Migration guards — pure checks that run without a DB.

The actual up/down round-trip is exercised on dev Aurora (CI / founder-run with the DB env); these
catch the cheap, common mistakes before that: a branched revision graph (two heads) and a model that
drifted from the columns a migration is supposed to add.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models import (
    ApprovalLink,
    ApprovalTemplate,
    Batch,
    Brief,
    Campaign,
    CampaignLead,
    Company,
    MessageVariant,
    OutreachEvent,
    Prospect,
    ProspectApproval,
    ResearchJob,
    ResearchRun,
    ScopeOverride,
    ScoringJob,
    Tenant,
)

_ALEMBIC = Path(__file__).resolve().parents[3] / "infra" / "alembic"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(_ALEMBIC / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ALEMBIC))
    return ScriptDirectory.from_config(cfg)


def test_single_alembic_head():
    """One linear history — a second head means two migrations share a down_revision."""
    assert _script_dir().get_heads() == ["0029_sending_account"]


def test_0011_columns_present_on_models():
    """The C1 columns the migration adds must exist on the ORM models (and seed_limit be gone)."""
    assert "apollo_org_id" in Company.__table__.columns
    assert "apollo_person_id" in Prospect.__table__.columns
    assert "seed_limit" not in Tenant.__table__.columns
    cons = {c.name for c in Company.__table__.constraints}
    assert "uq_company_tenant_apollo_org" in cons


def test_0012_scope_override_model_matches_migration():
    """The 0012 table the migration creates must match the ORM model (columns + unique key)."""
    cols = set(ScopeOverride.__table__.columns.keys())
    assert cols == {"id", "tenant_id", "kind", "params", "created_at", "updated_at"}
    cons = {c.name for c in ScopeOverride.__table__.constraints}
    assert "uq_scope_override_tenant_kind" in cons


def test_0014_fit_reason_and_index_cleanup():
    """0014 adds prospect.fit_reason (parity with company) + the composite list-sort indexes, and
    drops the UNIQUE-covered single-column indexes — the ORM must reflect the same end state. (The
    0014 fit-score sort indexes `ix_*_tenant_fit` were themselves dropped in 0026 / V2-4.)"""
    assert "fit_reason" in Prospect.__table__.columns
    p_idx = {i.name for i in Prospect.__table__.indexes}
    assert "ix_prospect_tenant_fit" not in p_idx  # dropped in 0026 (V2-4 contraction)
    assert "ix_prospect_identity_key" not in p_idx
    c_idx = {i.name for i in Company.__table__.indexes}
    assert "ix_company_tenant_fit" not in c_idx  # dropped in 0026 (V2-4 contraction)
    assert "ix_company_domain" not in c_idx
    assert "ix_brief_tenant_id" not in {i.name for i in Brief.__table__.indexes}


def test_0015_scoring_job_model_matches_migration():
    """0015 creates `scoring_job` (the W4 async-scoring tracker) — the ORM model must match the
    columns + index the migration builds."""
    cols = set(ScoringJob.__table__.columns.keys())
    assert cols == {"id", "tenant_id", "kind", "params", "status", "result", "error",
                    "created_at", "updated_at"}
    assert "ix_scoring_job_tenant_kind" in {i.name for i in ScoringJob.__table__.indexes}


def test_0016_phase_d_models_match_migration():
    """0016 creates the four Phase D tables — the ORM models must match the columns + keys the
    migration builds (the masking serializer + billing rows depend on this exact shape)."""
    assert set(Batch.__table__.columns.keys()) == {
        "id", "tenant_id", "icp_id", "name", "status", "sent_at", "decided_at", "created_at"
    }
    assert "ix_batch_tenant_created" in {i.name for i in Batch.__table__.indexes}

    assert set(ProspectApproval.__table__.columns.keys()) == {
        "id", "tenant_id", "batch_id", "prospect_id", "decision", "decided_at", "created_at"
    }
    pa_cons = {c.name for c in ProspectApproval.__table__.constraints}
    assert "uq_prospect_approval_batch_prospect" in pa_cons

    assert set(ApprovalLink.__table__.columns.keys()) == {
        "id", "tenant_id", "batch_id", "recipient_email", "token_hash", "expires_at",
        "used_at", "created_at"
    }
    assert set(ApprovalTemplate.__table__.columns.keys()) == {
        "id", "tenant_id", "data", "created_at", "updated_at"
    }
    assert "uq_approval_template_tenant" in {
        c.name for c in ApprovalTemplate.__table__.constraints
    }


def test_0028_phase_e_models_match_migration():
    """0028 creates the four Phase E tables — the ORM models must match the columns + keys the
    migration builds (the funnel SoT + webhook dedupe depend on this exact shape)."""
    assert set(Campaign.__table__.columns.keys()) == {
        "id", "tenant_id", "batch_id", "icp_id", "name", "smartlead_campaign_id", "status",
        "settings", "created_at", "updated_at"
    }
    c_cons = {c.name for c in Campaign.__table__.constraints}
    assert "uq_campaign_batch" in c_cons  # 1:1 with an approved batch
    assert "uq_campaign_tenant_smartlead" in c_cons

    assert set(MessageVariant.__table__.columns.keys()) == {
        "id", "tenant_id", "campaign_id", "key", "subject", "body", "is_winner",
        "created_at", "updated_at"
    }
    assert "uq_message_variant_campaign_key" in {
        c.name for c in MessageVariant.__table__.constraints
    }

    assert set(CampaignLead.__table__.columns.keys()) == {
        "id", "tenant_id", "campaign_id", "prospect_id", "approval_id", "smartlead_lead_id",
        "stage", "stage_changed_at", "variant_key", "created_at"
    }
    assert "uq_campaign_lead_campaign_prospect" in {
        c.name for c in CampaignLead.__table__.constraints
    }
    # approval_id is the billable-evidence hop — RESTRICT (undeletable while referenced).
    approval_fk = next(
        fk
        for fk in CampaignLead.__table__.foreign_keys
        if fk.column.table.name == "prospect_approval"
    )
    assert approval_fk.ondelete == "RESTRICT"

    assert set(OutreachEvent.__table__.columns.keys()) == {
        "id", "tenant_id", "campaign_id", "campaign_lead_id", "event_type", "smartlead_event_id",
        "payload", "triage", "handled_at", "response_body", "occurred_at", "created_at"
    }
    assert "ix_outreach_event_tenant_type_created" in {
        i.name for i in OutreachEvent.__table__.indexes
    }


def test_0029_sending_account_model_matches_migration():
    """0029 moves the Smartlead sending-inbox pool out of the secret into `sending_account` — the
    ORM must match the columns + the per-tenant unique the launch worker's account read needs."""
    from app.models import SendingAccount

    assert set(SendingAccount.__table__.columns.keys()) == {
        "id", "tenant_id", "smartlead_account_id", "from_email", "from_name", "status",
        "created_at", "updated_at"
    }
    assert "uq_sending_account_tenant_smartlead" in {
        c.name for c in SendingAccount.__table__.constraints
    }
    assert "ix_sending_account_tenant" in {i.name for i in SendingAccount.__table__.indexes}


def test_0019_scope_lineage_columns_present_on_models():
    """0019 adds the three nullable scope-lineage columns to research_run — the ORM must reflect
    them (the Find-history drawer + Stage-3 page cursor read these)."""
    cols = ResearchRun.__table__.columns
    assert "filter_body" in cols
    assert "scope_source" in cols
    assert "result_meta" in cols
    # All nullable — pre-0019 runs read NULL, no backfill.
    assert cols["filter_body"].nullable
    assert cols["scope_source"].nullable
    assert cols["result_meta"].nullable


def test_0024_v2_label_columns_present_on_models():
    """0024 adds the scoring-v2 contract columns (label/score_total on both) + the label-bucketed
    list index — the ORM must reflect the same end state. All nullable (no backfill). `verified` was
    dropped 2026-07-09 (founder: not meaningful) — it must exist on neither model."""
    for model in (Company, Prospect):
        cols = model.__table__.columns
        assert "label" in cols and cols["label"].nullable
        assert "score_total" in cols and cols["score_total"].nullable
        assert "verified" not in cols
        # V2-4 (0026) retired the v1 verdict columns — label/score_total are the whole contract now.
        assert "fit_score" not in cols and "fit_tier" not in cols
    # The label-bucketed index on both; the v1 fit index was dropped in 0026 (V2-4).
    assert "ix_company_tenant_label" in {i.name for i in Company.__table__.indexes}
    assert "ix_prospect_tenant_label" in {i.name for i in Prospect.__table__.indexes}
    assert "ix_company_tenant_fit" not in {i.name for i in Company.__table__.indexes}


def test_0027_dplus_indexes_present_on_models():
    """0027 (D+.5 F1) adds the score-sorted feed composites on company/prospect, the scoring_job
    active-job partial unique index, and the research_run scan index; and drops the two
    single-column tenant indexes. The ORM must reflect the same end state."""
    c_idx = {i.name for i in Company.__table__.indexes}
    p_idx = {i.name for i in Prospect.__table__.indexes}
    assert "ix_company_tenant_score" in c_idx
    assert "ix_prospect_tenant_score" in p_idx
    # R29a — the composite prefix-covers these, so they were dropped.
    assert "ix_company_tenant_id" not in c_idx
    assert "ix_prospect_tenant_id" not in p_idx
    # R9 — the active-job partial unique index (one queued/running job per tenant×kind).
    sj_idx = {i.name: i for i in ScoringJob.__table__.indexes}
    active = sj_idx.get("uq_scoring_job_active_tenant_kind")
    assert active is not None and active.unique
    # N8 — the structuring active-job partial unique (one queued/running job per tenant; no kind).
    rj_idx = {i.name: i for i in ResearchJob.__table__.indexes}
    rj_active = rj_idx.get("uq_research_job_active_tenant")
    assert rj_active is not None and rj_active.unique
    # R22a — the research_run scan index; N49 — its single-column tenant index is dropped (covered).
    rr_idx = {i.name for i in ResearchRun.__table__.indexes}
    assert "ix_research_run_tenant_created" in rr_idx
    assert "ix_research_run_tenant_id" not in rr_idx

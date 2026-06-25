"""Migration guards — pure checks that run without a DB.

The actual up/down round-trip is exercised on dev Aurora (CI / founder-run with the DB env); these
catch the cheap, common mistakes before that: a branched revision graph (two heads) and a model that
drifted from the columns a migration is supposed to add.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models import Brief, Company, Prospect, ScopeOverride, ScoringJob, Tenant

_ALEMBIC = Path(__file__).resolve().parents[3] / "infra" / "alembic"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(_ALEMBIC / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ALEMBIC))
    return ScriptDirectory.from_config(cfg)


def test_single_alembic_head():
    """One linear history — a second head means two migrations share a down_revision."""
    assert _script_dir().get_heads() == ["0015_scoring_job"]


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
    drops the UNIQUE-covered single-column indexes — the ORM must reflect the same end state."""
    assert "fit_reason" in Prospect.__table__.columns
    p_idx = {i.name for i in Prospect.__table__.indexes}
    assert "ix_prospect_tenant_fit" in p_idx
    assert "ix_prospect_identity_key" not in p_idx
    c_idx = {i.name for i in Company.__table__.indexes}
    assert "ix_company_tenant_fit" in c_idx
    assert "ix_company_domain" not in c_idx
    assert "ix_brief_tenant_id" not in {i.name for i in Brief.__table__.indexes}


def test_0015_scoring_job_model_matches_migration():
    """0015 creates `scoring_job` (the W4 async-scoring tracker) — the ORM model must match the
    columns + index the migration builds."""
    cols = set(ScoringJob.__table__.columns.keys())
    assert cols == {"id", "tenant_id", "kind", "params", "status", "result", "error",
                    "created_at", "updated_at"}
    assert "ix_scoring_job_tenant_kind" in {i.name for i in ScoringJob.__table__.indexes}

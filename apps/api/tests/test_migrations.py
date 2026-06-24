"""Migration guards — pure checks that run without a DB.

The actual up/down round-trip is exercised on dev Aurora (CI / founder-run with the DB env); these
catch the cheap, common mistakes before that: a branched revision graph (two heads) and a model that
drifted from the columns a migration is supposed to add.
"""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory

from app.models import Company, Prospect, ScopeOverride, Tenant

_ALEMBIC = Path(__file__).resolve().parents[3] / "infra" / "alembic"


def _script_dir() -> ScriptDirectory:
    cfg = Config(str(_ALEMBIC / "alembic.ini"))
    cfg.set_main_option("script_location", str(_ALEMBIC))
    return ScriptDirectory.from_config(cfg)


def test_single_alembic_head():
    """One linear history — a second head means two migrations share a down_revision."""
    assert _script_dir().get_heads() == ["0013_split_fit_rubric"]


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

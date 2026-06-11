"""seed — HoldSlot tenant #0 + two founder owners

Revision ID: 0002_seed
Revises: 0001_baseline
Create Date: 2026-06-11

The build-stage password is read from HOLDSLOT_SEED_PASSWORD at migration time and
argon2-hashed here — no plaintext or hash is committed. Production forces a reset via the
password_reset flow, so this temporary credential never reaches a real client. Idempotent:
re-running upgrades is a no-op (ON CONFLICT DO NOTHING).
"""

import os
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from argon2 import PasswordHasher

revision: str = "0002_seed"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TENANT_SLUG = "holdslot"
TENANT_NAME = "HoldSlot"
FOUNDERS = [
    ("jason.tse@tryholdslot.com", "Jason Tse"),
    ("jason.wong@tryholdslot.com", "Jason Wong"),
]


def upgrade() -> None:
    password = os.environ.get("HOLDSLOT_SEED_PASSWORD")
    if not password:
        raise RuntimeError(
            "HOLDSLOT_SEED_PASSWORD must be set to run the seed migration "
            "(build-stage founder password; never committed)."
        )
    ph = PasswordHasher()
    bind = op.get_bind()

    bind.execute(
        sa.text(
            "INSERT INTO tenant (slug, name) VALUES (:slug, :name) "
            "ON CONFLICT (slug) DO NOTHING"
        ),
        {"slug": TENANT_SLUG, "name": TENANT_NAME},
    )
    tenant_id = bind.execute(
        sa.text("SELECT id FROM tenant WHERE slug = :slug"), {"slug": TENANT_SLUG}
    ).scalar_one()

    for email, full_name in FOUNDERS:
        bind.execute(
            sa.text(
                "INSERT INTO app_user (email, password_hash, full_name) "
                "VALUES (:email, :hash, :full_name) ON CONFLICT (email) DO NOTHING"
            ),
            {"email": email, "hash": ph.hash(password), "full_name": full_name},
        )
        user_id = bind.execute(
            sa.text("SELECT id FROM app_user WHERE email = :email"), {"email": email}
        ).scalar_one()
        bind.execute(
            sa.text(
                "INSERT INTO membership (user_id, tenant_id, role) "
                "VALUES (CAST(:user_id AS uuid), CAST(:tenant_id AS uuid), 'owner') "
                "ON CONFLICT (user_id, tenant_id) DO NOTHING"
            ),
            {"user_id": str(user_id), "tenant_id": str(tenant_id)},
        )


def downgrade() -> None:
    bind = op.get_bind()
    emails = [e for e, _ in FOUNDERS]
    # Memberships cascade when the users are removed.
    bind.execute(
        sa.text("DELETE FROM app_user WHERE email = ANY(:emails)"), {"emails": emails}
    )
    bind.execute(sa.text("DELETE FROM tenant WHERE slug = :slug"), {"slug": TENANT_SLUG})

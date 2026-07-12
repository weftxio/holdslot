"""Phase G billing API schemas — owner subscription/activation doors + the read (GS4/GS6)."""

from __future__ import annotations

from pydantic import BaseModel


class SubscriptionIn(BaseModel):
    plan: str  # free · launch · growth


class SubscriptionOut(BaseModel):
    plan: str
    status: str  # active · past_due · canceled · incomplete
    stripe_customer_id: str | None = None
    stripe_subscription_id: str | None = None
    activation_paid_at: str | None = None
    enrichment_cap: int = 0
    icp_limit: int = 0
    current_month_usage: int = 0
    usage_month: str | None = None
    overage_enabled: bool = True


class BillingStatusOut(BaseModel):
    """The GS6 ledger line — `subscription` is null until the tenant is on Stripe (dormant today).
    """

    subscription: SubscriptionOut | None = None

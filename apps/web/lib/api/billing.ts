// --- Phase G (GS6) — billing status (Stripe). Ships dormant: every tenant today has no subscription,
// and the endpoint is deploy-gated (FR-7), so a null subscription OR a 404 both render as "no billing
// yet" — identical to today. Never throws (so the ledger page degrades cleanly).

import { authFetch } from "./core";

export type BillingSubscriptionApi = {
  plan: string;
  status: string;
  stripe_customer_id: string | null;
  stripe_subscription_id: string | null;
  activation_paid_at: string | null;
  enrichment_cap: number;
  icp_limit: number;
  current_month_usage: number;
  usage_month: string | null;
  overage_enabled: boolean;
};
export type BillingStatusApi = { subscription: BillingSubscriptionApi | null };
export async function getBillingStatus(client: string): Promise<BillingStatusApi> {
  try {
    const r = await authFetch(`/${client}/billing/status`);
    if (!r.ok) return { subscription: null };
    return r.json();
  } catch {
    return { subscription: null };
  }
}

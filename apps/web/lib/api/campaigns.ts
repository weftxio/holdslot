// --- Phase E (S4/S5) — Outreach campaigns + reply queue ----------------------
// All counts/metrics are DERIVED server-side from the outreach_event ledger, never stored. The
// funnel single source of truth is campaign_lead.stage; the vocabulary matches the Campaign tab's
// SAMPLE_FUNNEL ids (contacted · followup · replied · meeting · noshow · billable · drop).

import { authFetch, detail } from "./core";

export type VariantApi = {
  key: string;
  subject: string;
  body: string;
  is_winner: boolean;
  sent: number;
  opens: number;
  replies: number;
};
export type CampaignApi = {
  id: string;
  batch_id: string;
  batch_name: string;
  name: string;
  icp: string;
  status: string; // draft | launching | sending | paused | completed | error
  lead_total: number;
  stages: Record<string, number>; // current stage → lead count
  created_at: string | null;
};
// One row in a lead's per-card timeline — derived server-side from the outreach_event ledger.
export type LeadEventApi = {
  event_type: string;
  direction: "out" | "in" | "sys";
  title: string;
  summary: string;
  occurred_at: string | null;
};
// One prospect in the funnel (a campaign_lead ⋈ its enrichment + timeline). Grouped by `company`
// into the Campaign-tab cards; `stage` is the funnel single source of truth.
export type LeadApi = {
  id: string;
  prospect_name: string;
  prospect_role: string;
  company: string;
  stage: string;
  variant_key: string | null;
  opened: boolean;
  replied: boolean;
  events: LeadEventApi[];
};
export type CampaignDetailApi = CampaignApi & { variants: VariantApi[]; leads: LeadApi[] };

export async function listCampaigns(client: string): Promise<CampaignApi[]> {
  const r = await authFetch(`/${client}/campaigns`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function getCampaign(client: string, id: string): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns/${id}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function createCampaign(
  client: string,
  body: { batch_id: string; name?: string; variants?: { key: string; subject: string; body: string }[] }
): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r)); // 409 unless the batch is approved
  return r.json();
}
export async function launchCampaign(client: string, id: string): Promise<CampaignApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/launch`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function replaceVariants(
  client: string,
  id: string,
  variants: { key: string; subject: string; body: string }[]
): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/variants`, {
    method: "PUT",
    json: true,
    body: JSON.stringify({ variants }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function setVariantWinner(
  client: string,
  id: string,
  key: string
): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/winner`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ key }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function pauseCampaign(client: string, id: string): Promise<CampaignApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/pause`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function resumeCampaign(client: string, id: string): Promise<CampaignApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/resume`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function syncCampaign(client: string, id: string): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns/${id}/sync`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// Manually move one lead to another funnel stage (the Campaign-tab "Move stage…" dropdown). Runs
// through the same server allowed-moves guard as every transition — an illegal move is a 409.
export async function moveLeadStage(
  client: string,
  campaignId: string,
  leadId: string,
  stage: string
): Promise<CampaignDetailApi> {
  const r = await authFetch(`/${client}/campaigns/${campaignId}/leads/${leadId}/move`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ stage }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Cross-campaign reply-triage inbox. pip = unhandled count (handled_at IS NULL); `state=open`
// restricts to those. Triage classes seed from the mock vocabulary as plain strings.
export type ReplyApi = {
  id: string;
  campaign_id: string;
  campaign_name: string;
  prospect_name: string;
  prospect_role: string;
  stage: string;
  reply_body: string;
  subject: string;
  occurred_at: string | null;
  triage: string | null;
  handled_at: string | null;
  response_body: string | null;
};
export async function listReplies(
  client: string,
  opts?: { state?: "all" | "open"; campaignId?: string }
): Promise<ReplyApi[]> {
  const q = new URLSearchParams();
  if (opts?.state) q.set("state", opts.state);
  if (opts?.campaignId) q.set("campaign_id", opts.campaignId);
  const qs = q.toString();
  const r = await authFetch(`/${client}/replies${qs ? `?${qs}` : ""}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function triageReply(
  client: string,
  eventId: string,
  triage: string
): Promise<ReplyApi> {
  const r = await authFetch(`/${client}/replies/${eventId}/triage`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ triage }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function respondReply(
  client: string,
  eventId: string,
  body: string,
  opts?: { includeBookingLink?: boolean }
): Promise<ReplyApi> {
  const r = await authFetch(`/${client}/replies/${eventId}/respond`, {
    method: "POST",
    json: true,
    // include_booking_link (F3) mints + threads a fresh booking link — the one carrier.
    body: JSON.stringify({ body, include_booking_link: !!opts?.includeBookingLink }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

// Performance-summary (EF-Q9) — derived on read. The Leads funnel + reply stats + needs-attention ①
// go live at E7; the meeting cells (headline, held, billable, calendar, ②③) go live at F5.
type FunnelStageApi = { label: string; n: number };
export type MeetingCalendarItemApi = {
  id: string;
  scheduled_at: string; // UTC …Z; render viewer-local
  prospect_name: string;
  outcome: string | null;
};
export type PerformanceSummaryApi = {
  funnel: FunnelStageApi[];
  new_positive_replies: number;
  replies_awaiting_review: number;
  approvals_pending: number;
  qualified_last_30d: number;
  qualified_delta: number;
  meetings_held_week: number;
  show_up_rate: number | null;
  awaiting_this_week: number;
  billable_this_cycle: number;
  open_booking_links: number;
  held_without_feedback: number;
  calendar: MeetingCalendarItemApi[];
};
export async function getPerformanceSummary(client: string): Promise<PerformanceSummaryApi> {
  const r = await authFetch(`/${client}/performance-summary`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

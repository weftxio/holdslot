// --- External public pages (token-only — NO auth) ----------------------------
// Bare fetch, no auth — the token IS the credential. Every GET always 200s with a `state` so the
// page can pick its pane and never leak tenant existence; a submit's ONE "this link is gone" signal
// is a 410 (everything else — 409 slot-taken, 503 cold-start, network — is transient). Covers the
// three client-facing flows: Phase-D approval, Phase-F booking, Phase-F feedback.

import { API_BASE, fail } from "./core";

// The MASKED client view: fit context only, never a clear-text identity/contact vector. Composed
// into ApprovalViewApi (the exported parent); not imported standalone.
type ApprovalProspectApi = {
  id: string; // the opaque decide handle (prospect_approval id)
  name: string; // "Sarah K."
  company_descriptor: string; // "SaaS · 200–500 · US" (not the exact company)
  title: string;
  fit_reason: string;
};
export type ApprovalViewApi = {
  state: "valid" | "expired" | "used";
  batch_name: string;
  client_name: string;
  prospects: ApprovalProspectApi[];
};
export type ApprovalDecisionApi = { status: string; approved: number; removed: number };

export async function getApproval(token: string): Promise<ApprovalViewApi> {
  // No auth — the token is the credential. The endpoint always 200s with a `state` so the page
  // can pick its pane; it never reveals tenant existence.
  const r = await fetch(`${API_BASE}/approve/${encodeURIComponent(token)}`);
  if (!r.ok) return fail(r);
  return r.json();
}
export async function decideApproval(
  token: string,
  body: { removed_ids?: string[]; approved_ids?: string[]; request_changes?: boolean }
): Promise<ApprovalDecisionApi> {
  const r = await fetch(`${API_BASE}/approve/${encodeURIComponent(token)}/decide`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return fail(r); // 410 once expired/used/decided (ApiError carries the status)
  return r.json();
}

export type BookingViewApi = {
  state: "valid" | "used" | "expired";
  client_name: string;
  duration_min: number;
  slots: string[]; // UTC …Z instants; group by the viewer's local day
  expires_at: string | null;
};
export async function getBookingView(token: string): Promise<BookingViewApi> {
  const r = await fetch(`${API_BASE}/book/${encodeURIComponent(token)}`);
  if (!r.ok) return fail(r);
  return r.json();
}
export type BookingConfirmApi = { state: string };
export async function submitBooking(token: string, slot: string): Promise<BookingConfirmApi> {
  const r = await fetch(`${API_BASE}/book/${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ slot }),
  });
  // ApiError.status lets the page react per-code: 400 tampered · 409 taken · 410 used · 503 retry.
  if (!r.ok) return fail(r);
  return r.json();
}

export type FeedbackViewApi = {
  state: "valid" | "used" | "expired";
  client_name: string;
  expires_at: string | null;
};
export async function getFeedbackView(token: string): Promise<FeedbackViewApi> {
  const r = await fetch(`${API_BASE}/feedback/${encodeURIComponent(token)}`);
  if (!r.ok) return fail(r);
  return r.json();
}
export async function submitFeedback(
  token: string,
  body: { rating: number; chips: string[]; comment: string }
): Promise<{ state: string }> {
  const r = await fetch(`${API_BASE}/feedback/${encodeURIComponent(token)}`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!r.ok) return fail(r); // 410 once used (ApiError carries the status)
  return r.json();
}

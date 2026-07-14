// --- Phase F (S6) — meetings · bookings · feedback (authed console reads) -----
// Console reads run the on-read sweep server-side before returning. The client-facing token pages
// (book/feedback GET+POST) live in `external.ts`.

import { authFetch, detail } from "./core";

export type MeetingApi = {
  id: string;
  prospect_name: string;
  company_name: string;
  campaign_name: string;
  campaign_id: string | null; // M27 — filters key off id, not the non-unique campaign name
  batch_name: string;
  scheduled_at: string;
  held: boolean | null;
  outcome: string | null; // qualified · short_call · noshow
  amount: number | null;
  billing_chip: string; // Held · Billed · Not billable
  disputed: boolean;
  feedback_state: string; // Received · None
  feedback_rating: number | null;
  won: boolean | null;
};
export async function listMeetings(
  client: string,
  when: "upcoming" | "past" = "past"
): Promise<MeetingApi[]> {
  const r = await authFetch(`/${client}/meetings?when=${when}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export type SweepResultApi = { swept: number; qualified: number; noshow: number };
export async function refreshMeetings(client: string): Promise<SweepResultApi> {
  const r = await authFetch(`/${client}/meetings/refresh`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function correctOutcome(
  client: string,
  meetingId: string,
  body: { outcome: string; disputed?: boolean; won?: boolean }
): Promise<MeetingApi> {
  const r = await authFetch(`/${client}/meetings/${meetingId}/outcome`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// NF-3 — the dedicated `won` setter (deal-outcome flag only; never touches outcome/amount).
export async function setMeetingWon(
  client: string,
  meetingId: string,
  won: boolean | null
): Promise<MeetingApi> {
  const r = await authFetch(`/${client}/meetings/${meetingId}/won`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ won }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export type BookingRowApi = {
  id: string;
  prospect_name: string;
  company_name: string;
  campaign_name: string;
  status: string; // Confirmed · Awaiting confirm · Expired
  invitation_preview: string;
  reply_event_id: string | null; // the Propose-new-time carrier handle
  sent_at: string | null;
  expires_at: string | null;
};
export async function listBookings(client: string): Promise<BookingRowApi[]> {
  const r = await authFetch(`/${client}/bookings`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

export type FeedbackRowApi = {
  id: string; // meeting id
  prospect_name: string;
  company_name: string;
  state: string; // Received · Pending · None
  overdue: boolean;
  rating: number | null;
  comment: string;
  feedback_at: string | null;
  scheduled_at: string;
};
export async function listFeedback(client: string): Promise<FeedbackRowApi[]> {
  const r = await authFetch(`/${client}/feedback`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function sendFeedbackForm(client: string, meetingId: string): Promise<FeedbackRowApi> {
  const r = await authFetch(`/${client}/meetings/${meetingId}/feedback/send`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function informClient(client: string, meetingId: string): Promise<void> {
  const r = await authFetch(`/${client}/meetings/${meetingId}/inform-client`, { method: "POST" });
  if (!r.ok) throw new Error(await detail(r));
}

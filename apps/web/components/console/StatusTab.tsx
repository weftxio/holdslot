// Shared constants for the Client Action (client-status) tabs. The active tab is now derived from
// the URL (real nested routes), so no React context is needed — the sidebar, the client-status
// layout, and the topbar breadcrumb/back-button all read these constants + the pathname.

export type StatusTabKey = "approval" | "booking" | "feedback";

export const STATUS_TABS: [StatusTabKey, string][] = [
  ["approval", "List Approval"],
  ["booking", "Booking Status"],
  ["feedback", "Meeting Feedback"],
];
// S25 — derived from STATUS_TABS so the label strings live in exactly one place.
export const STATUS_LABEL = Object.fromEntries(STATUS_TABS) as Record<StatusTabKey, string>;
// Per-tab "back to <workspace tab>" target, rendered in the topbar-right by ConsoleShell.
export const STATUS_BACK: Record<StatusTabKey, [string, string]> = {
  approval: ["workspace/batches", "Back to Approval Batches"],
  booking: ["workspace/campaign", "Back to Outreach Campaigns"],
  feedback: ["workspace/summaries", "Back to Meeting Recaps"],
};

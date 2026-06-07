"use client";
import { createContext, useContext } from "react";

export type StatusTabKey = "approval" | "booking" | "feedback";

export const STATUS_TABS: [StatusTabKey, string][] = [
  ["approval", "List Approval"],
  ["booking", "Booking Status"],
  ["feedback", "Meeting Feedback"],
];
export const STATUS_LABEL: Record<StatusTabKey, string> = {
  approval: "List Approval",
  booking: "Booking Status",
  feedback: "Meeting Feedback",
};
// Per-tab "back to <workspace tab>" target, rendered in the topbar-right by ConsoleShell.
export const STATUS_BACK: Record<StatusTabKey, [string, string]> = {
  approval: ["workspace#batches", "Back to Approval Batches"],
  booking: ["workspace#campaign", "Back to Outreach Campaigns"],
  feedback: ["workspace#summaries", "Back to Meeting Recaps"],
};

// Shared so the sidebar, the client-status page, and the topbar breadcrumb all agree on
// the active tab without relying on hashchange events (which Next's client router doesn't fire).
export const StatusTabCtx = createContext<{ tab: StatusTabKey; setTab: (t: StatusTabKey) => void }>(
  {
    tab: "approval",
    setTab: () => {},
  }
);
export const useStatusTab = () => useContext(StatusTabCtx);

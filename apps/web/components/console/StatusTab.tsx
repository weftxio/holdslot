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

// Shared so the sidebar, the client-status page, and the topbar breadcrumb all agree on
// the active tab without relying on hashchange events (which Next's client router doesn't fire).
export const StatusTabCtx = createContext<{ tab: StatusTabKey; setTab: (t: StatusTabKey) => void }>(
  {
    tab: "approval",
    setTab: () => {},
  }
);
export const useStatusTab = () => useContext(StatusTabCtx);

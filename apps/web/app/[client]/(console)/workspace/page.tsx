"use client";
import { useHashRedirect } from "@/lib/nav";

const VALID = ["brief", "list", "batches", "campaign", "replies", "summaries", "billing"] as const;

// The workspace tabs are now real routes (./brief, ./list, …). This index redirects to the default
// tab, translating legacy hash links (/workspace#batches) and preserving the query so the ?batch=
// deep-link from the Client Status status log still opens the requested batch.
export default function WorkspaceIndex() {
  useHashRedirect("workspace", VALID, "brief", true);
  return null;
}

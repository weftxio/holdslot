"use client";
import { useHashRedirect } from "@/lib/nav";

const VALID = ["approval", "booking", "feedback"] as const;

// The Client Action tabs are now real routes (./approval, ./booking, ./feedback). This index
// redirects to the default tab, translating legacy hash links (/client-status#booking) that may
// live in old emails/bookmarks. The query string is preserved for symmetry with the workspace index.
export default function ClientStatusIndex() {
  useHashRedirect("client-status", VALID, "approval", true);
  return null;
}

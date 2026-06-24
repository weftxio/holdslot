"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

const VALID = ["brief", "list", "batches", "campaign", "replies", "summaries", "billing"] as const;
type Tab = (typeof VALID)[number];

// The workspace tabs are now real routes (./brief, ./list, …). This index redirects to the default
// tab, and translates legacy hash links (/workspace#batches) that may live in old emails/bookmarks
// — and the ?batch= deep-link from the Client Status status log — to the matching route, preserving
// the query so the batches route can still open the requested batch.
export default function WorkspaceIndex() {
  const { client } = useParams<{ client: string }>();
  const router = useRouter();
  useEffect(() => {
    const h = location.hash.slice(1) as Tab;
    const target = (VALID as readonly string[]).includes(h) ? h : "brief";
    router.replace(`/${client}/workspace/${target}${location.search}`);
  }, [client, router]);
  return null;
}

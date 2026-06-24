"use client";
import { useEffect } from "react";
import { useParams, useRouter } from "next/navigation";

/** The active `[client]` slug from the route. Client components only. */
export function useClient(): string {
  return useParams<{ client: string }>().client;
}

// Redirects a tab "index" route (e.g. /workspace) to its default sub-route, translating legacy
// `#hash` links (/workspace#batches) that may still live in old emails/bookmarks. With
// `preserveSearch`, the query string (the ?batch= deep-link) is carried through the redirect.
export function useHashRedirect(
  base: string,
  valid: readonly string[],
  fallback: string,
  preserveSearch = false,
) {
  const client = useClient();
  const router = useRouter();
  useEffect(() => {
    const h = location.hash.slice(1);
    const target = valid.includes(h) ? h : fallback;
    const search = preserveSearch ? location.search : "";
    router.replace(`/${client}/${base}/${target}${search}`);
  }, [client, router, base, valid, fallback, preserveSearch]);
}

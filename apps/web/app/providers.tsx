"use client";
import { useState } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";

// App-wide TanStack Query client. The workspace tabs are real nested routes, so a tab page
// unmounts on navigation and would otherwise refetch its whole API payload on every return.
// This QueryClient lives ABOVE the routes (mounted in the root layout), so the workspace pages
// read their per-client data through it as a cross-navigation cache: a tab-return within
// `staleTime` resolves from cache with no network call. One client per browser session (created
// once via useState so it survives re-renders but never leaks between SSR requests).
export function Providers({ children }: { children: React.ReactNode }) {
  const [client] = useState(
    () =>
      new QueryClient({
        defaultOptions: {
          queries: {
            // Tab-return within 30s is a pure cache hit (no refetch). After that, the next read
            // refetches in the background while showing the cached rows (stale-while-revalidate).
            staleTime: 30_000,
            // Keep cached payloads around long enough to span real navigation (leave workspace,
            // visit Performance Summary, come back) before they're garbage-collected.
            gcTime: 10 * 60_000,
            // The data layer (lib/api.ts) already does its own auth-refresh + 503 cold-start retry;
            // don't double-retry on top of it, and don't refetch on window focus (the workspace is
            // edit-heavy — a focus-driven refetch would be surprising).
            retry: false,
            refetchOnWindowFocus: false,
          },
        },
      })
  );
  return <QueryClientProvider client={client}>{children}</QueryClientProvider>;
}

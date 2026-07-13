"use client";
import { createContext, useCallback, useContext, useMemo, type ReactNode } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  listBatches,
  listCampaigns,
  listMeetings,
  listReplies,
  type CampaignApi,
  type ReplyApi,
} from "@/lib/api";
import { useClient } from "@/lib/nav";
import { batchFromApi } from "@/lib/workspace/constants";
import type { Batch, Recap } from "@/lib/workspace/types";

// The cross-tab state that must survive sub-route navigation. The workspace tabs are real nested
// routes, so each route page unmounts on navigation — anything shared between tabs (the batches a
// campaign links to; the campaigns a reply/summary filter reads; the reply queue itself, whose
// unhandled count drives the tab pip) lives here in a provider mounted by the workspace layout,
// above all the sub-routes.
//
// NF-2: the four loaders now ride the app-wide TanStack Query cache (the same one the Business
// Brief tab already uses), keyed per client. A tab-return within `staleTime` is a pure cache hit —
// no refetch storm — and keying by `client` structurally retires the old N14 in-flight-switch guard
// (a client switch changes the query key, so a stale fetch can never overwrite the new client's
// rows). The provider's exposed shape is UNCHANGED — `reload*` are thin `invalidateQueries`
// wrappers and `setReplies` a `setQueryData` wrapper — so every consumer keeps working verbatim.
type WorkspaceCtx = {
  // batches / campaigns are read-only to consumers — mutated only via their live reload (the
  // create/send/launch flows refresh through it), so there's no setter escape hatch.
  batches: Batch[];
  reloadBatches: () => Promise<void>;
  campaigns: CampaignApi[];
  reloadCampaigns: () => Promise<void>;
  // Replies keep a setter for optimistic triage/respond updates; reloadReplies re-syncs from server.
  replies: ReplyApi[];
  reloadReplies: () => Promise<void>;
  setReplies: React.Dispatch<React.SetStateAction<ReplyApi[]>>;
  // Recaps are derived from the held `meeting` rows (F5) — loaded on mount + refreshable.
  recaps: Recap[];
  reloadMeetings: () => Promise<void>;
};

const Ctx = createContext<WorkspaceCtx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const client = useClient();
  const queryClient = useQueryClient();

  // The four cross-tab queries. An auth/cold-start failure leaves `data` undefined (retry:false is
  // set globally — the data layer already does its own refresh/503 retry), so the `?? []` fallback
  // renders an empty tab rather than throwing — the same safe default the old catch blocks gave.
  const batchesQ = useQuery({ queryKey: ["batches", client], queryFn: () => listBatches(client) });
  const campaignsQ = useQuery({
    queryKey: ["campaigns", client],
    queryFn: () => listCampaigns(client),
  });
  const repliesQ = useQuery({ queryKey: ["replies", client], queryFn: () => listReplies(client) });
  const meetingsQ = useQuery({
    queryKey: ["meetings", client, "past"],
    queryFn: () => listMeetings(client, "past"),
  });

  const batches = useMemo(() => (batchesQ.data ?? []).map(batchFromApi), [batchesQ.data]);
  const campaigns = campaignsQ.data ?? [];
  const replies = repliesQ.data ?? [];
  // Recaps = held meetings only (a meeting summary is for a meeting that happened).
  const recaps = useMemo<Recap[]>(
    () =>
      (meetingsQ.data ?? [])
        .filter((r) => r.held)
        .map((r) => ({
          id: r.id,
          campaign: r.campaign_name,
          campaignId: r.campaign_id, // M27 — id-keyed filter
          batch: r.batch_name,
          prospectName: r.prospect_name,
          companyName: r.company_name,
          scheduledAt: r.scheduled_at,
          outcome: r.outcome,
          rating: r.feedback_rating,
          disputed: r.disputed, // M33 — outcome-correction UI reads/writes this
          won: r.won, // tri-state passthrough (NF-3): true | false | null (undecided)
        })),
    [meetingsQ.data]
  );

  // A reload = invalidate its query; with the observer mounted here (always, while the workspace
  // is open) that triggers a refetch and the returned promise resolves once the fresh rows land —
  // so an awaiting caller (create/send/launch/triage) still sees updated data on resolve.
  const reloadBatches = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["batches", client] }).then(() => {}),
    [queryClient, client]
  );
  const reloadCampaigns = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["campaigns", client] }).then(() => {}),
    [queryClient, client]
  );
  const reloadReplies = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["replies", client] }).then(() => {}),
    [queryClient, client]
  );
  const reloadMeetings = useCallback(
    () => queryClient.invalidateQueries({ queryKey: ["meetings", client, "past"] }).then(() => {}),
    [queryClient, client]
  );

  // Optimistic triage/respond writes go straight to the replies cache — same `useState` setter
  // signature (value or updater), now backed by setQueryData so a later reloadReplies re-syncs.
  const setReplies = useCallback<React.Dispatch<React.SetStateAction<ReplyApi[]>>>(
    (update) => {
      queryClient.setQueryData<ReplyApi[]>(["replies", client], (prev) => {
        const base = prev ?? [];
        return typeof update === "function"
          ? (update as (p: ReplyApi[]) => ReplyApi[])(base)
          : update;
      });
    },
    [queryClient, client]
  );

  return (
    <Ctx.Provider
      value={{
        batches,
        reloadBatches,
        campaigns,
        reloadCampaigns,
        replies,
        reloadReplies,
        setReplies,
        recaps,
        reloadMeetings,
      }}
    >
      {children}
    </Ctx.Provider>
  );
}

export function useWorkspace(): WorkspaceCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return v;
}

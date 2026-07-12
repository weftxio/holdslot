"use client";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
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
// Phase E: `campaigns` and `replies` are now LIVE — loaded from the API on mount and refreshable
// (create/launch/triage/respond call the matching reload). Only `recaps` (meeting summaries) stays
// mock until Phase F writes the `meeting` moves.
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
  const [batches, setBatches] = useState<Batch[]>([]);
  const [campaigns, setCampaigns] = useState<CampaignApi[]>([]);
  const [replies, setReplies] = useState<ReplyApi[]>([]);
  const [recaps, setRecaps] = useState<Recap[]>([]);
  // Always holds the latest client so an in-flight reload can detect a switch and drop its result.
  // Updated in the mount/client-change effect below (not during render — refs must not be written
  // in the render body).
  const clientRef = useRef(client);

  const reloadBatches = useCallback(async () => {
    try {
      const rows = await listBatches(client);
      // N14 — a switch during the fetch would otherwise overwrite the NEW client's rows with the old
      // client's (a cross-client leak). Bail if the active client moved on.
      if (clientRef.current !== client) return;
      setBatches(rows.map(batchFromApi));
    } catch {
      // Auth/cold-start failures surface via the console SessionGuard; an empty list is the safe
      // default here so the tab still renders.
      if (clientRef.current !== client) return;
      setBatches([]);
    }
  }, [client]);

  const reloadCampaigns = useCallback(async () => {
    try {
      const rows = await listCampaigns(client);
      if (clientRef.current !== client) return;
      setCampaigns(rows);
    } catch {
      if (clientRef.current !== client) return;
      setCampaigns([]);
    }
  }, [client]);

  const reloadReplies = useCallback(async () => {
    try {
      const rows = await listReplies(client);
      if (clientRef.current !== client) return;
      setReplies(rows);
    } catch {
      if (clientRef.current !== client) return;
      setReplies([]);
    }
  }, [client]);

  const reloadMeetings = useCallback(async () => {
    try {
      const rows = await listMeetings(client, "past");
      if (clientRef.current !== client) return;
      // Recaps = held meetings only (a meeting summary is for a meeting that happened).
      setRecaps(
        rows
          .filter((r) => r.held)
          .map((r) => ({
            id: r.id,
            campaign: r.campaign_name,
            batch: r.batch_name,
            prospectName: r.prospect_name,
            companyName: r.company_name,
            scheduledAt: r.scheduled_at,
            outcome: r.outcome,
            rating: r.feedback_rating,
            won: !!r.won,
          }))
      );
    } catch {
      if (clientRef.current !== client) return;
      setRecaps([]);
    }
  }, [client]);

  useEffect(() => {
    // Load the cross-tab data on mount / client change — data-sync effects (external → React), not
    // derived state; each setState lands after its awaited fetch. Stamp the current client BEFORE the
    // fetches so a stale in-flight reload (from a prior client) bails on resolve.
    clientRef.current = client;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadBatches();
    void reloadCampaigns();
    void reloadReplies();
    void reloadMeetings();
  }, [client, reloadBatches, reloadCampaigns, reloadReplies, reloadMeetings]);

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

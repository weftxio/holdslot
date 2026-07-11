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
import { listBatches } from "@/lib/api";
import { useClient } from "@/lib/nav";
import { batchFromApi } from "@/lib/workspace/constants";
import { INITIAL_REPLIES } from "@/lib/workspace/fixtures";
import type { Batch, Campaign, Reply } from "@/lib/workspace/types";

// The cross-tab state that must survive sub-route navigation. The workspace tabs are real nested
// routes, so each route page unmounts on navigation — anything shared between tabs (the batches a
// campaign links to; the campaigns a reply/recap filter reads; the reply queue itself) lives here
// in a provider mounted by the workspace layout, above all the sub-routes.
//
// Phase D: `batches` is now LIVE — loaded from the API on mount and refreshable via `reloadBatches`
// (create/send call it). `campaigns`/`replies` stay mock until Phase E.
type WorkspaceCtx = {
  // batches are read-only to consumers — mutated only via the live `reloadBatches` (create/send
  // refresh through it), so there's no `setBatches` escape hatch.
  batches: Batch[];
  reloadBatches: () => Promise<void>;
  campaigns: Campaign[];
  setCampaigns: React.Dispatch<React.SetStateAction<Campaign[]>>;
  replies: Reply[];
  setReplies: React.Dispatch<React.SetStateAction<Reply[]>>;
};

const Ctx = createContext<WorkspaceCtx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const client = useClient();
  const [batches, setBatches] = useState<Batch[]>([]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([
    { name: "Campaign 1", batch: "Batch 1", locked: true },
    { name: "Campaign 2", batch: "Batch 2", locked: true },
  ]);
  const [replies, setReplies] = useState<Reply[]>(INITIAL_REPLIES);
  // Always holds the latest client so an in-flight reload can detect a switch and drop its result.
  // Updated in the mount/client-change effect below (not during render — refs must not be written
  // in the render body).
  const clientRef = useRef(client);

  const reloadBatches = useCallback(async () => {
    try {
      const rows = await listBatches(client);
      // N14 — a switch during the fetch would otherwise overwrite the NEW client's batches with the
      // old client's rows (a cross-client leak). Bail if the active client moved on.
      if (clientRef.current !== client) return;
      setBatches(rows.map(batchFromApi));
    } catch {
      // Auth/cold-start failures surface via the console SessionGuard; an empty list is the safe
      // default here so the tab still renders.
      if (clientRef.current !== client) return;
      setBatches([]);
    }
  }, [client]);

  useEffect(() => {
    // Load batches on mount / client change — a data-sync effect (external → React), not derived
    // state; the setState lands after the awaited fetch inside reloadBatches. Stamp the current
    // client BEFORE the fetch so a stale in-flight reload (from a prior client) bails on resolve.
    clientRef.current = client;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void reloadBatches();
  }, [reloadBatches, client]);

  return (
    <Ctx.Provider
      value={{
        batches,
        reloadBatches,
        campaigns,
        setCampaigns,
        replies,
        setReplies,
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

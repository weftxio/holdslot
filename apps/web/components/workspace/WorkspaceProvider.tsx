"use client";
import { createContext, useContext, useState, type ReactNode } from "react";
import type { Batch, Campaign, Reply } from "@/lib/workspace/types";
import { INITIAL_REPLIES } from "@/lib/workspace/fixtures";

// The cross-tab mock state that must survive sub-route navigation. The workspace tabs are now real
// nested routes, so each route page unmounts on navigation — anything shared between tabs (the
// batches a campaign links to; the campaigns a reply/recap filter reads; the reply queue itself)
// lives here in a provider mounted by the workspace layout, above all the sub-routes.
type WorkspaceCtx = {
  batches: Batch[];
  setBatches: React.Dispatch<React.SetStateAction<Batch[]>>;
  campaigns: Campaign[];
  setCampaigns: React.Dispatch<React.SetStateAction<Campaign[]>>;
  replies: Reply[];
  setReplies: React.Dispatch<React.SetStateAction<Reply[]>>;
};

const Ctx = createContext<WorkspaceCtx | null>(null);

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  // Batches / campaigns
  const [batches, setBatches] = useState<Batch[]>([
    {
      name: "Batch 1",
      count: 40,
      approved: 40,
      icp: "ICP A",
      status: "Approved",
      createdAt: "2026-05-20",
      sentAt: "2026-05-21",
      approvedAt: "2026-05-23",
    },
    {
      name: "Batch 2",
      count: 52,
      approved: 52,
      icp: "ICP A",
      status: "Approved",
      createdAt: "2026-05-26",
      sentAt: "2026-05-27",
      approvedAt: "2026-05-29",
    },
    {
      name: "Batch 3",
      count: 48,
      approved: 0,
      icp: "ICP B",
      status: "Pending",
      createdAt: "2026-06-01",
      sentAt: "2026-06-01",
    },
  ]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([
    { name: "Campaign 1", batch: "Batch 1", locked: true },
    { name: "Campaign 2", batch: "Batch 2", locked: true },
  ]);
  // Replies
  const [replies, setReplies] = useState<Reply[]>(INITIAL_REPLIES);

  return (
    <Ctx.Provider value={{ batches, setBatches, campaigns, setCampaigns, replies, setReplies }}>
      {children}
    </Ctx.Provider>
  );
}

export function useWorkspace(): WorkspaceCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useWorkspace must be used within a WorkspaceProvider");
  return v;
}

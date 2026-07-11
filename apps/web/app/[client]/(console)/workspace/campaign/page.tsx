"use client";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { useClient } from "@/lib/nav";
import { CampaignTab } from "../CampaignTab";

export default function CampaignPage() {
  const client = useClient();
  const { batches, campaigns, reloadCampaigns } = useWorkspace();
  // Campaigns can only be created from client-approved batches — pending/rejected batches are never
  // selectable, so a launched campaign is always safe to send (the server re-checks: 409 otherwise).
  const approvedBatches = batches.filter((b) => b.status === "Approved");

  return (
    <section className="tabpane active">
      <CampaignTab
        client={client}
        campaigns={campaigns}
        batchOptions={approvedBatches.map((b) => ({ id: b.id, name: b.name, count: b.count }))}
        reloadCampaigns={reloadCampaigns}
      />
    </section>
  );
}

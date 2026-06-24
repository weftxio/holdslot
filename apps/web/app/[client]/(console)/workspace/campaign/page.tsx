"use client";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { CampaignTab } from "../CampaignTab";

export default function CampaignPage() {
  const toast = useToast();
  const { batches, campaigns, setCampaigns } = useWorkspace();
  // Campaigns can only be linked to client-approved batches — pending/rejected
  // batches are never selectable, so a linked campaign is always safe to send.
  const approvedBatches = batches.filter((b) => b.status === "Approved");

  return (
    <section className="tabpane active">
      <CampaignTab
        campaigns={campaigns}
        batchOptions={approvedBatches.map((b) => ({ name: b.name, count: b.count }))}
        onNewCampaign={() => {
          const batch = approvedBatches[0]?.name;
          if (!batch) {
            toast("Approve a sendout batch first", "warn");
            return null;
          }
          // Derive the next number from existing names (not the count) so a
          // prior rename can't make this collide with a live campaign name.
          const taken = new Set(campaigns.map((c) => c.name));
          let n = campaigns.length + 1;
          while (taken.has("Campaign " + n)) n++;
          const name = "Campaign " + n;
          setCampaigns((s) => [...s, { name, batch, locked: false }]);
          toast(name + " created · pick a batch and confirm");
          return name;
        }}
        onSetBatch={(name, batch) =>
          setCampaigns((s) => s.map((c) => (c.name === name ? { ...c, batch } : c)))
        }
        onConfirm={(name) => {
          setCampaigns((s) => s.map((c) => (c.name === name ? { ...c, locked: true } : c)));
          toast("Batch locked · " + name + " confirmed");
        }}
        onRename={(oldName, newName) =>
          setCampaigns((s) => s.map((c) => (c.name === oldName ? { ...c, name: newName } : c)))
        }
      />
    </section>
  );
}

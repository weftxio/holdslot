// --- Phase D (S3) — Sendout batch + client approval --------------------------
// Counts (total/approved/removed/pending) are DERIVED server-side from prospect_approval, never
// stored. `status` walks draft → sent → approved | changes_requested.

import { authFetch, detail } from "./core";

export type BatchApi = {
  id: string;
  name: string;
  icp: string;
  status: string;
  total: number;
  approved: number;
  removed: number;
  pending: number;
  created_at: string | null;
  sent_at: string | null;
  decided_at: string | null;
};
// One prospect inside the console (FULL, operator-owned) batch detail — NOT masked. Composed into
// BatchDetailApi (the exported parent); not imported standalone.
type BatchProspectApi = {
  approval_id: string;
  prospect_id: string;
  full_name: string;
  title: string;
  decision: string; // pending | approved | removed
};
type BatchCompanyGroupApi = {
  company: string;
  domain: string;
  industry: string;
  prospects: BatchProspectApi[];
};
export type BatchDetailApi = BatchApi & { companies: BatchCompanyGroupApi[] };
export type ApprovalTemplateApi = { subject: string; body: string; cta: string };

export async function listBatches(client: string): Promise<BatchApi[]> {
  const r = await authFetch(`/${client}/batches`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function createBatch(
  client: string,
  body: { prospect_ids: string[]; name?: string; icp_id?: string | null }
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function getBatch(client: string, id: string): Promise<BatchDetailApi> {
  const r = await authFetch(`/${client}/batches/${id}`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function sendApproval(
  client: string,
  id: string,
  email: string
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches/${id}/send`, {
    method: "POST",
    json: true,
    body: JSON.stringify({ email }),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// Step-3 human fallback — the operator records the client decision by hand.
export async function decideBatch(
  client: string,
  id: string,
  body: { approved_ids?: string[]; removed_ids?: string[]; request_changes?: boolean }
): Promise<BatchApi> {
  const r = await authFetch(`/${client}/batches/${id}/decide`, {
    method: "POST",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
// Hard-delete a batch; the server cascades its prospect_approval + approval_link rows. 204, no body.
export async function deleteBatch(client: string, id: string): Promise<void> {
  const r = await authFetch(`/${client}/batches/${id}`, { method: "DELETE" });
  if (!r.ok) throw new Error(await detail(r));
}
export async function getApprovalTemplate(client: string): Promise<ApprovalTemplateApi> {
  const r = await authFetch(`/${client}/approval-template`);
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}
export async function saveApprovalTemplate(
  client: string,
  body: ApprovalTemplateApi
): Promise<ApprovalTemplateApi> {
  const r = await authFetch(`/${client}/approval-template`, {
    method: "PUT",
    json: true,
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await detail(r));
  return r.json();
}

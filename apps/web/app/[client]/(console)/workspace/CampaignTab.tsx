"use client";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { highlightBody } from "@/lib/tmpl";
import { nameInitials } from "@/lib/initials";
import { parseUtc } from "@/lib/dates";
import {
  createCampaign,
  getCampaign,
  launchCampaign,
  moveLeadStage,
  pauseCampaign,
  replaceVariants,
  resumeCampaign,
  setVariantWinner,
  syncCampaign,
  type CampaignApi,
  type CampaignDetailApi,
  type LeadApi,
  type LeadEventApi,
  type VariantApi,
} from "@/lib/api";

// ── Outreach Campaigns · funnel view (Phase E — LIVE) ────────────────────────
// A campaign is a 7-stage funnel; `campaign_lead.stage` is the single source of truth and every
// count/metric is DERIVED server-side from the outreach_event ledger (never stored). This tab is a
// thin adapter: it fetches the live campaign detail and renders it through the design's funnel /
// variant / company-card structure. Actions map to real endpoints (create · launch · pause/resume ·
// sync · variant winner/edit · per-lead stage move); affordances with no backend at MVP (per-person
// "Send", LinkedIn channel) are intentionally absent.

type StageKind = "wip" | "bill" | "exit" | "stop";

// Static presentation for the seven stages — the design's copy. Live counts + prospects overlay it.
// Only the outreach step (`contacted`) carries the campaign's A/B/C message variants (the backend
// holds one campaign-level variant set = the outreach sequence; later stages are same-thread sends).
const STAGE_META: { id: string; kind: StageKind; title: string; step: string; obj: string; hasVariants: boolean }[] = [
  { id: "contacted", kind: "wip", title: "Initial outreach", step: "S3", obj: "Get the email opened and earn a first reply.", hasVariants: true },
  { id: "followup", kind: "wip", title: "Follow-up", step: "S4", obj: "Re-engage non-responders before the sequence ends.", hasVariants: false },
  { id: "replied", kind: "wip", title: "Positive reply", step: "S4→S5", obj: "Convert a positive reply into a booked meeting.", hasVariants: false },
  { id: "meeting", kind: "wip", title: "Meeting schedule", step: "S5", obj: "Prospect shows up and passes the fit check.", hasVariants: false },
  { id: "noshow", kind: "exit", title: "No show", step: "S5", obj: "Booked but did not attend · re-book or park.", hasVariants: false },
  { id: "billable", kind: "bill", title: "Qualified billable", step: "S6", obj: "Held meeting confirmed · pushed to Stripe.", hasVariants: false },
  { id: "drop", kind: "stop", title: "Drop / DNC", step: "S4", obj: "Graceful exit on negative or do-not-contact replies.", hasVariants: false },
];
const STAGE_TITLE: Record<string, string> = Object.fromEntries(STAGE_META.map((s) => [s.id, s.title]));

// Allowed stage moves — mirrors the server allowed-moves map (an illegal move is a 409). Note the
// `contacted → replied` rung (a first-email reply is legitimate before any follow-up); it is the one
// flex the server map adds over the original mock, reconciled here.
const MOVES: Record<string, string[]> = {
  contacted: ["followup", "replied", "drop"],
  followup: ["contacted", "replied", "drop"],
  replied: ["followup", "meeting", "drop"],
  meeting: ["replied", "billable", "noshow", "drop"],
  noshow: ["meeting", "replied", "drop"],
  billable: ["meeting", "drop"],
  drop: ["contacted"],
};

const LOGO = ["#5e7c9e", "#3e8e6e", "#9bb7d6", "#c08a3e", "#c25b53", "#4a6b7a"];
const logoFor = (s: string) => LOGO[[...s].reduce((a, c) => a + c.charCodeAt(0), 0) % LOGO.length];
const pct = (num: number, den: number) => (den > 0 ? Math.round((num / den) * 100) : 0);

function fmtWhen(iso: string | null): string {
  // parseUtc pins a timezone-naive instant to UTC so the ledger row renders in the viewer's own
  // zone — a bare `new Date(iso)` read the UTC digits as LOCAL (M6/R16).
  const d = parseUtc(iso);
  if (!d) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

// Human status label per campaign status (the server vocabulary).
const STATUS_LABEL: Record<string, string> = {
  draft: "Draft",
  launching: "Launching…",
  sending: "Sending",
  paused: "Paused",
  completed: "Completed",
  error: "Error",
};
const STATUS_BADGE: Record<string, string> = {
  draft: "badge-neutral",
  launching: "badge-info",
  sending: "badge-ok",
  paused: "badge-warn",
  completed: "badge-info",
  error: "badge-danger",
};

// ── Component ────────────────────────────────────────────────────────────────
export function CampaignTab({
  client,
  campaigns,
  batchOptions,
  reloadCampaigns,
}: {
  client: string;
  campaigns: CampaignApi[];
  batchOptions: { id: string; name: string; count: number }[];
  reloadCampaigns: () => Promise<void>;
}) {
  const toast = useToast();
  const [selectedId, setSelectedId] = useState<string>("");
  const [detail, setDetail] = useState<CampaignDetailApi | null>(null);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [stageId, setStageId] = useState("contacted");
  const [openLogs, setOpenLogs] = useState<Set<string>>(new Set());
  const [editKey, setEditKey] = useState<string | null>(null); // variant key being edited (draft)
  const [editSubject, setEditSubject] = useState("");
  const [editBody, setEditBody] = useState("");
  const [creating, setCreating] = useState(false);
  const [newBatchId, setNewBatchId] = useState<string>("");
  const reqRef = useRef(0); // guards against a stale detail fetch overwriting a newer one

  // The active campaign — the explicit selection if it's still in the live list, else the first one
  // (derived during render, so no reconciling set-state effect). Empty when the client has none.
  const resolvedId = campaigns.some((c) => c.id === selectedId)
    ? selectedId
    : campaigns[0]?.id ?? "";

  const loadDetail = useCallback(
    async (id: string) => {
      if (!id) {
        setDetail(null);
        return;
      }
      const req = ++reqRef.current;
      setLoading(true);
      try {
        const d = await getCampaign(client, id);
        if (reqRef.current === req) setDetail(d);
      } catch {
        if (reqRef.current === req) setDetail(null);
      } finally {
        if (reqRef.current === req) setLoading(false);
      }
    },
    [client]
  );

  useEffect(() => {
    // Data-sync effect (external → React): fetch the selected campaign's detail. The setState lands
    // inside the awaited loadDetail; the reqRef guard drops a stale response.
    // eslint-disable-next-line react-hooks/set-state-in-effect
    void loadDetail(resolvedId);
  }, [resolvedId, loadDetail]);

  // The create-batch dropdown defaults to the first approved batch (derived, not stored — avoids a
  // set-state effect); an explicit pick overrides it.
  const effectiveBatchId = newBatchId || batchOptions[0]?.id || "";

  const selectStage = (id: string) => {
    setStageId(id);
    setOpenLogs(new Set());
  };

  // ── derived view (from live detail) ──
  const stageCounts = useMemo(() => detail?.stages ?? {}, [detail]);
  const leadTotal = detail?.lead_total ?? 0;
  const status = detail?.status ?? "draft";
  const maxVol = Math.max(...STAGE_META.map((s) => stageCounts[s.id] ?? 0), 1);
  const meta = STAGE_META.find((s) => s.id === stageId) ?? STAGE_META[0];

  const kpis = useMemo(
    () => [
      { lbl: "Prospects", val: leadTotal },
      { lbl: "Replies", val: stageCounts.replied ?? 0 },
      { lbl: "Meetings", val: (stageCounts.meeting ?? 0) + (stageCounts.billable ?? 0) },
      { lbl: "Billable", val: stageCounts.billable ?? 0, accent: true },
    ],
    [leadTotal, stageCounts]
  );

  // Leads in the selected stage, grouped into company cards.
  const cards = useMemo(() => groupByCompany((detail?.leads ?? []).filter((l) => l.stage === stageId)), [detail, stageId]);

  // ── actions ──
  const refresh = useCallback(async () => {
    await Promise.all([loadDetail(resolvedId), reloadCampaigns()]);
  }, [loadDetail, resolvedId, reloadCampaigns]);

  // Returns true iff `fn` resolved — so a caller can toast success / clear its edit buffer only
  // AFTER the write lands, never optimistically (M26).
  const guard = async (label: string, fn: () => Promise<unknown>): Promise<boolean> => {
    if (busy) return false;
    setBusy(true);
    try {
      await fn();
      return true;
    } catch (e) {
      toast(e instanceof Error ? e.message : label + " failed", "warn");
      return false;
    } finally {
      setBusy(false);
    }
  };

  const handleCreate = () =>
    guard("Create campaign", async () => {
      if (!effectiveBatchId) {
        toast("Approve a sendout batch first", "warn");
        return;
      }
      const created = await createCampaign(client, { batch_id: effectiveBatchId });
      await reloadCampaigns();
      setSelectedId(created.id);
      setDetail(created);
      setCreating(false);
      selectStage("contacted");
      toast(`${created.name} created · author variants, then launch`);
    });

  const handleLaunch = () =>
    guard("Launch", async () => {
      await launchCampaign(client, resolvedId);
      await refresh();
      toast("Launch started · leads are being pushed to Smartlead");
    });

  const handlePause = () =>
    guard("Pause", async () => {
      // pause/resume return the truncated CampaignOut (no variants/leads) — refetch the full detail.
      await pauseCampaign(client, resolvedId);
      await refresh();
      toast("Campaign paused");
    });

  const handleResume = () =>
    guard("Resume", async () => {
      await resumeCampaign(client, resolvedId);
      await refresh();
      toast("Campaign resumed");
    });

  const handleSync = () =>
    guard("Sync", async () => {
      const d = await syncCampaign(client, resolvedId);
      setDetail(d);
      toast("Synced with Smartlead");
    });

  const handleWinner = (key: string) =>
    guard("Set winner", async () => {
      const d = await setVariantWinner(client, resolvedId, key);
      setDetail(d);
      toast(`Variant ${key} marked as the winner`);
    });

  const handleMove = (leadId: string, target: string) => {
    if (!MOVES[stageId]?.includes(target)) return;
    void guard("Move", async () => {
      const d = await moveLeadStage(client, resolvedId, leadId, target);
      setDetail(d);
      await reloadCampaigns();
      setOpenLogs(new Set());
      toast(`Moved to ${STAGE_TITLE[target]}`);
    });
  };

  // Variant editing is only legal on a draft (Smartlead sequences lock once launched). The edit
  // buffer lives here (lifted out of the card) so the card is controlled — no set-state effect.
  const canEditVariants = status === "draft";
  const startEdit = (v: VariantApi) => {
    setEditKey(v.key);
    setEditSubject(v.subject);
    setEditBody(v.body);
  };
  const persistVariants = (next: VariantApi[]) =>
    guard("Save variants", async () => {
      const d = await replaceVariants(
        client,
        resolvedId,
        next.map((v) => ({ key: v.key, subject: v.subject, body: v.body }))
      );
      setDetail(d);
    });

  // M26 — clear the edit buffer + toast only AFTER the PUT resolves. The old code toasted "saved"
  // and dropped the draft synchronously, so a failed save showed a false success and lost the edit.
  const saveVariant = () => {
    if (!editKey) return;
    const key = editKey;
    const cur = detail?.variants ?? [];
    void persistVariants(
      cur.map((v) => (v.key === key ? { ...v, subject: editSubject, body: editBody } : v))
    ).then((ok) => {
      if (!ok) return; // keep the draft open on failure (guard already warned)
      setEditKey(null);
      toast(`Variant ${key} saved`);
    });
  };
  const addVariant = () => {
    const cur = detail?.variants ?? [];
    let code = 65;
    while (cur.some((v) => v.key === String.fromCharCode(code))) code++;
    const key = String.fromCharCode(code);
    void persistVariants([
      ...cur.map((v) => ({ ...v })),
      { key, subject: "", body: "New variant · write your message. Use {{first_name}} and {{company_name}} tokens.", is_winner: false, sent: 0, opens: 0, replies: 0 },
    ]).then((ok) => ok && toast("Variant added"));
  };
  const deleteVariant = (key: string) => {
    const cur = detail?.variants ?? [];
    if (cur.length <= 1) {
      toast("Keep at least one variant", "warn");
      return;
    }
    void persistVariants(cur.filter((v) => v.key !== key)).then(
      (ok) => ok && toast(`Variant ${key} removed`, "warn")
    );
  };

  const toggleLog = (pid: string) =>
    setOpenLogs((s) => {
      const next = new Set(s);
      next.has(pid) ? next.delete(pid) : next.add(pid);
      return next;
    });

  const showCreate = creating || campaigns.length === 0;
  const outreachVariants = detail?.variants ?? [];

  return (
    <>
      {/* Top bar: campaign selector + KPIs + batch / status controls */}
      <div className="cmp-top">
        {campaigns.length > 0 && (
          <label className="cmp-top-field">
            <select
              className="select select-sm"
              aria-label="Campaign"
              value={resolvedId}
              onChange={(e) => {
                setSelectedId(e.target.value);
                setCreating(false);
                selectStage("contacted");
              }}
            >
              {campaigns.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </label>
        )}
        {detail && !showCreate && (
          <span className={clsx("badge", STATUS_BADGE[status] ?? "badge-neutral")} title="Campaign status">
            <span className="bdot" />
            {STATUS_LABEL[status] ?? status}
          </span>
        )}

        <div className="cmp-top-actions">
          <div className="cmp-kpis">
            {kpis.map((k) => (
              <div key={k.lbl} className={clsx("cmp-kpi", k.accent && "accent")}>
                <div className="cmp-kpi-lbl">{k.lbl}</div>
                <div className="cmp-kpi-val">{k.val}</div>
              </div>
            ))}
          </div>

          {showCreate ? (
            <div className="cmp-batch draft">
              <span className="cmp-batch-lbl">Sendout batch</span>
              <select
                className="select select-sm"
                value={effectiveBatchId}
                aria-label="Select an approved sendout batch"
                onChange={(e) => setNewBatchId(e.target.value)}
                disabled={batchOptions.length === 0}
              >
                {batchOptions.length === 0 ? (
                  <option value="">No approved batches</option>
                ) : (
                  batchOptions.map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name} · {b.count}
                    </option>
                  ))
                )}
              </select>
              <button
                type="button"
                className="btn btn-accent btn-sm"
                onClick={handleCreate}
                disabled={busy || batchOptions.length === 0}
              >
                Create campaign
              </button>
              {campaigns.length > 0 && (
                <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCreating(false)}>
                  Cancel
                </button>
              )}
            </div>
          ) : (
            <div className="cmp-batch" title="Sendout batch · locked to this campaign">
              <svg className="cmp-batch-lock" width="12" height="12" viewBox="0 0 14 14" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="6.2" width="8" height="5.5" rx="1.2" />
                <path d="M4.6 6.2V4.6a2.4 2.4 0 0 1 4.8 0v1.6" />
              </svg>
              <span className="cmp-batch-lbl">Sendout batch</span>
              <span className="cmp-batch-name">{detail?.batch_name || "·"}</span>
            </div>
          )}

          {/* Status-driven primary action */}
          {!showCreate && detail && (
            <>
              {(status === "draft" || status === "error") && (
                <button type="button" className="btn btn-accent btn-sm" onClick={handleLaunch} disabled={busy}>
                  {status === "error" ? "Retry launch" : "Launch"}
                </button>
              )}
              {status === "sending" && (
                <>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={handleSync} disabled={busy}>
                    Sync
                  </button>
                  <button type="button" className="btn btn-ghost btn-sm" onClick={handlePause} disabled={busy}>
                    Pause
                  </button>
                </>
              )}
              {status === "paused" && (
                <button type="button" className="btn btn-accent btn-sm" onClick={handleResume} disabled={busy}>
                  Resume
                </button>
              )}
            </>
          )}

          {!showCreate && (
            <button type="button" className="btn btn-ghost btn-sm" onClick={() => setCreating(true)}>
              ＋ New campaign
            </button>
          )}
        </div>
      </div>

      {/* Body */}
      {showCreate ? (
        <div className="cmp-empty" style={{ marginTop: 24 }}>
          {batchOptions.length === 0
            ? "Approve a sendout batch on the Sendout Batch tab first, then create a campaign from it."
            : "Pick an approved batch above and create a campaign to begin outreach."}
        </div>
      ) : loading && !detail ? (
        <div className="cmp-empty" style={{ marginTop: 24 }}>
          Loading campaign…
        </div>
      ) : (
        <div className="cmp-shell">
          {/* Funnel rail */}
          <aside className="cmp-rail">
            <div className="cmp-eyebrow">Funnel · click a stage</div>
            <div className="cmp-funnel">
              {STAGE_META.map((s) => {
                const vol = stageCounts[s.id] ?? 0;
                return (
                  <button
                    key={s.id}
                    type="button"
                    className={clsx("cmp-stage", s.id === stageId && "active")}
                    data-kind={s.kind}
                    onClick={() => selectStage(s.id)}
                  >
                    <div className="cmp-stage-top">
                      <span className="cmp-sw" />
                      <span className="cmp-nm">{s.title}</span>
                      <span className="cmp-ct">{vol}</span>
                    </div>
                    <div className="cmp-bar">
                      <i style={{ width: `${Math.max(6, Math.round((vol / maxVol) * 100))}%` }} />
                    </div>
                    <div className="cmp-conv">
                      <b>{vol === 0 ? "No leads yet" : `${vol} ${vol === 1 ? "lead" : "leads"}`}</b>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>

          {/* Detail */}
          <main className="cmp-detail">
            {/* Variant testing · only on the outreach stage (the campaign's A/B/C sequence) */}
            {meta.hasVariants && (
              <>
                <div className="cmp-sec">
                  A/B variant testing
                  <span className="cmp-pill">
                    {outreachVariants.length} {outreachVariants.length === 1 ? "variant" : "variants"}
                    {!canEditVariants && " · locked"}
                  </span>
                </div>
                {outreachVariants.length === 0 ? (
                  <div className="cmp-empty">No variants yet · the server seeds a default on create.</div>
                ) : (
                  <VariantPanel
                    variants={outreachVariants}
                    canEdit={canEditVariants}
                    editKey={editKey}
                    editSubject={editSubject}
                    editBody={editBody}
                    onStartEdit={startEdit}
                    onCancelEdit={() => setEditKey(null)}
                    onEditSubject={setEditSubject}
                    onEditBody={setEditBody}
                    onSave={saveVariant}
                    onAdd={addVariant}
                    onDelete={deleteVariant}
                    onWinner={handleWinner}
                    busy={busy}
                  />
                )}
              </>
            )}

            {/* Prospects in stage */}
            <div className="cmp-sec">
              Prospects in this stage <span className="cmp-pill">{cards.length} companies</span>
            </div>
            {cards.length ? (
              <div className="cmp-cards">
                {cards.map((c, ci) => (
                  <CompanyCard
                    key={c.co + ci}
                    company={c}
                    stageId={stageId}
                    stageKind={meta.kind}
                    openLogs={openLogs}
                    onToggleLog={toggleLog}
                    onMove={handleMove}
                    busy={busy}
                  />
                ))}
              </div>
            ) : (
              <div className="cmp-empty">
                {leadTotal === 0
                  ? status === "draft"
                    ? "No prospects yet · launch the campaign to push the approved batch to Smartlead."
                    : "No prospects in the funnel yet."
                  : "No prospects in this stage yet"}
              </div>
            )}
          </main>
        </div>
      )}
    </>
  );
}

// ── grouping ──────────────────────────────────────────────────────────────────
type ViewCompany = { co: string; meta: string; people: LeadApi[] };
function groupByCompany(leads: LeadApi[]): ViewCompany[] {
  const map = new Map<string, ViewCompany>();
  for (const l of leads) {
    const co = l.company || "Unknown company";
    let group = map.get(co);
    if (!group) {
      group = { co, meta: "", people: [] };
      map.set(co, group);
    }
    group.people.push(l);
  }
  return [...map.values()];
}

// ── Variant panel ─────────────────────────────────────────────────────────────
// Controlled: the edit buffer (editSubject/editBody) is owned by CampaignTab, so the cards hold no
// local state and need no sync effect.
function VariantPanel({
  variants,
  canEdit,
  editKey,
  editSubject,
  editBody,
  onStartEdit,
  onCancelEdit,
  onEditSubject,
  onEditBody,
  onSave,
  onAdd,
  onDelete,
  onWinner,
  busy,
}: {
  variants: VariantApi[];
  canEdit: boolean;
  editKey: string | null;
  editSubject: string;
  editBody: string;
  onStartEdit: (v: VariantApi) => void;
  onCancelEdit: () => void;
  onEditSubject: (v: string) => void;
  onEditBody: (v: string) => void;
  onSave: () => void;
  onAdd: () => void;
  onDelete: (key: string) => void;
  onWinner: (key: string) => void;
  busy: boolean;
}) {
  return (
    <div className="cmp-vars">
      {variants.map((v) => {
        const editing = editKey === v.key;
        const openRate = pct(v.opens, v.sent);
        const replyRate = pct(v.replies, v.sent);
        return (
          <div key={v.key} className={clsx("cmp-v", v.is_winner && "win")}>
            <div className="cmp-vbadge">{v.key}</div>
            <div className="cmp-vmain">
              <div className="cmp-vtop">
                <span className="cmp-vname">Variant {v.key}</span>
                <button
                  type="button"
                  className={clsx("cmp-lead", !v.is_winner && "cmp-lead-off")}
                  title={v.is_winner ? "Winner" : "Mark as winner"}
                  onClick={() => onWinner(v.key)}
                  disabled={busy}
                >
                  <span className="cmp-lead-d" />
                  {v.is_winner ? "Winner" : "Set winner"}
                </button>
              </div>
              {editing ? (
                <>
                  <input
                    className="input cmp-vedit"
                    value={editSubject}
                    placeholder="Subject (blank on a follow-up = same-thread “Re:”)"
                    onChange={(e) => onEditSubject(e.target.value)}
                    style={{ marginBottom: 8 }}
                  />
                  <textarea className="textarea cmp-vedit" value={editBody} onChange={(e) => onEditBody(e.target.value)} />
                </>
              ) : (
                <div className="cmp-vcopy">
                  {v.subject && <div style={{ fontWeight: 600, marginBottom: 4 }}>{v.subject}</div>}
                  {highlightBody(v.body)}
                </div>
              )}
            </div>
            <div className="cmp-vmetrics">
              <div className="cmp-m">
                <div className="cmp-m-num">{openRate}%</div>
                <div className="cmp-m-cap">Open</div>
              </div>
              <div className="cmp-m">
                <div className={clsx("cmp-m-num", v.is_winner && "good")}>{replyRate}%</div>
                <div className="cmp-m-cap">Reply</div>
              </div>
            </div>
            {canEdit && (
              <div className="cmp-vact">
                {editing ? (
                  <>
                    <button
                      type="button"
                      className="cmp-vbtn edit active"
                      title={`Save variant ${v.key}`}
                      aria-label={`Save variant ${v.key}`}
                      onClick={onSave}
                      disabled={busy}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3.5 8.5l3 3 6-7" />
                      </svg>
                    </button>
                    <button type="button" className="cmp-vbtn del" title="Cancel" aria-label="Cancel edit" onClick={onCancelEdit}>
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M4 4l8 8M12 4l-8 8" />
                      </svg>
                    </button>
                  </>
                ) : (
                  <>
                    <button
                      type="button"
                      className="cmp-vbtn edit"
                      title={`Edit variant ${v.key}`}
                      aria-label={`Edit variant ${v.key}`}
                      onClick={() => onStartEdit(v)}
                      disabled={busy}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M11.5 2.5l2 2L6 12l-2.5.5L4 10z" />
                        <path d="M10 4l2 2" />
                      </svg>
                    </button>
                    <button
                      type="button"
                      className="cmp-vbtn del"
                      title={`Delete variant ${v.key}`}
                      aria-label={`Delete variant ${v.key}`}
                      onClick={() => onDelete(v.key)}
                      disabled={busy}
                    >
                      <svg width="14" height="14" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
                        <path d="M3 4.5h10M6.5 4.5V3h3v1.5M5 4.5l.5 8h5l.5-8" />
                      </svg>
                    </button>
                  </>
                )}
              </div>
            )}
          </div>
        );
      })}
      {canEdit && (
        <div className="cmp-vfoot">
          <button type="button" className="cmp-add" onClick={onAdd} disabled={busy}>
            ＋ Add variant
          </button>
        </div>
      )}
    </div>
  );
}

// ── Company card + people ──────────────────────────────────────────────────────
function personStatus(p: LeadApi) {
  if (p.replied) return <span className="cmp-rate">Replied</span>;
  if (p.opened) return <span className="cmp-rate">Opened</span>;
  return <span className="cmp-rate">Sent</span>;
}

function CompanyCard({
  company,
  stageId,
  stageKind,
  openLogs,
  onToggleLog,
  onMove,
  busy,
}: {
  company: ViewCompany;
  stageId: string;
  stageKind: StageKind;
  openLogs: Set<string>;
  onToggleLog: (pid: string) => void;
  onMove: (leadId: string, target: string) => void;
  busy: boolean;
}) {
  const targets = MOVES[stageId] ?? [];
  return (
    <div className="cmp-card" data-kind={stageKind}>
      <div className="cmp-crow">
        <div className="cmp-logo" style={{ background: logoFor(company.co) }}>
          {nameInitials(company.co)}
        </div>
        <div className="cmp-co">
          <div className="cmp-cname">{company.co}</div>
          {company.meta && <div className="cmp-cmeta">{company.meta}</div>}
        </div>
        <span className="cmp-pcount">
          {company.people.length} {company.people.length === 1 ? "contact" : "contacts"}
        </span>
      </div>
      <div className="cmp-people">
        {company.people.map((p) => {
          const open = openLogs.has(p.id);
          const log = p.events;
          return (
            <div key={p.id} className={clsx("cmp-person", open && "log-open")}>
              <div className="cmp-prow">
                <div className="cmp-av">{nameInitials(p.prospect_name || "?")}</div>
                <div className="cmp-pid">
                  <div className="cmp-pname">{p.prospect_name || "Unnamed prospect"}</div>
                  <div className="cmp-prole">{p.prospect_role}</div>
                </div>
                {p.variant_key && <span className="cmp-vsel locked">Var {p.variant_key}</span>}
              </div>
              <div className="cmp-pfoot">
                {personStatus(p)}
                <span className="cmp-spacer" />
                {log.length > 0 && (
                  <button type="button" className="cmp-logtoggle" aria-expanded={open} onClick={() => onToggleLog(p.id)}>
                    Log
                    <span className="cmp-logcount">{log.length}</span>
                    <span className="cmp-chev" aria-hidden>
                      ⌄
                    </span>
                  </button>
                )}
              </div>
              {log.length > 0 && (
                <div className="cmp-log-wrap">
                  <div className="cmp-log-inner">
                    {log.map((e: LeadEventApi, li) => (
                      <div key={li} className={clsx("cmp-logrow", e.direction)}>
                        <div className="cmp-lograil">
                          <span className="cmp-logdot" />
                        </div>
                        <div className="cmp-logbody">
                          <div className="cmp-logtop">
                            <span className="cmp-logch email">Email</span>
                            <span className="cmp-logtitle">{e.title}</span>
                            <span className="cmp-logwhen">{fmtWhen(e.occurred_at)}</span>
                          </div>
                          {e.summary && <div className="cmp-logmsg">{e.summary}</div>}
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
              {targets.length > 0 && (
                <div className="cmp-move">
                  <span className="cmp-move-lbl">Stage</span>
                  <select
                    className="cmp-movesel"
                    value=""
                    disabled={busy}
                    aria-label={`Move ${p.prospect_name} to another stage`}
                    onChange={(e) => {
                      if (e.target.value) onMove(p.id, e.target.value);
                    }}
                  >
                    <option value="" disabled>
                      Move stage…
                    </option>
                    {targets.map((id) => (
                      <option key={id} value={id}>
                        {STAGE_TITLE[id]}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

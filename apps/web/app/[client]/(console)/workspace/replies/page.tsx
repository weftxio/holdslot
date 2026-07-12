"use client";
import { useState } from "react";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import { useClient } from "@/lib/nav";
import { nameInitials } from "@/lib/initials";
import { respondReply, triageReply, type ReplyApi } from "@/lib/api";

// Cross-campaign reply-triage inbox (Phase E — LIVE). Each row is a `lead_replied` event ⋈ its lead
// + campaign. The operator classifies it (human triage — no LLM at MVP: positive → the lead advances
// to `replied`, negative → `drop`, the rest just clear the pip) and optionally sends an operator-
// authored threaded reply via Smartlead. The tab pip = unhandled count (handled_at IS NULL).

// Triage class → its badge + label (mirrors the mock's classification vocabulary).
const TRIAGE_META: { value: string; label: string; badge: string }[] = [
  { value: "positive", label: "Positive, wants a call", badge: "badge-ok" },
  { value: "objection-timing", label: "Objection: timing", badge: "badge-warn" },
  { value: "referral", label: "Referral: wrong person", badge: "badge-info" },
  { value: "nudge", label: "Nudge", badge: "badge-info" },
  { value: "negative", label: "Not interested", badge: "badge-danger" },
];
const triageMeta = (t: string | null) => TRIAGE_META.find((m) => m.value === t);

function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

export default function RepliesPage() {
  const toast = useToast();
  const client = useClient();
  const { replies, reloadReplies, campaigns } = useWorkspace();
  const [replyCamp, setReplyCamp] = useState("");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [bookLink, setBookLink] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<Set<string>>(new Set());

  const remaining = replies.filter((r) => !r.handled_at).length; // global total (matches the tab pip)
  const inView = replies.filter((r) => !replyCamp || r.campaign_name === replyCamp);
  const remainingInView = inView.filter((r) => !r.handled_at).length;

  const setDraft = (id: string, v: string) => setDrafts((s) => ({ ...s, [id]: v }));
  const withBusy = async (id: string, fn: () => Promise<unknown>) => {
    if (busy.has(id)) return;
    setBusy((s) => new Set(s).add(id));
    try {
      await fn();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Action failed", "warn");
    } finally {
      setBusy((s) => {
        const n = new Set(s);
        n.delete(id);
        return n;
      });
    }
  };

  const doTriage = (r: ReplyApi, value: string) =>
    withBusy(r.id, async () => {
      await triageReply(client, r.id, value);
      await reloadReplies();
      toast(`Classified · ${triageMeta(value)?.label ?? value}`);
    });

  const doRespond = (r: ReplyApi) =>
    withBusy(r.id, async () => {
      const text = (drafts[r.id] ?? "").trim();
      if (!text) {
        toast("Write a reply first", "warn");
        return;
      }
      const includeBookingLink = !!bookLink[r.id];
      await respondReply(client, r.id, text, { includeBookingLink });
      await reloadReplies();
      setDraft(r.id, "");
      toast(includeBookingLink ? "Reply sent with a booking link" : "Reply sent");
    });

  return (
    <section className="tabpane active">
      <div className="row" style={{ marginBottom: 18, justifyContent: "flex-end", flexWrap: "wrap", gap: 12 }}>
        {remaining > 0 ? (
          <span className="badge badge-warn">
            <span className="bdot" />
            {remaining} awaiting review
          </span>
        ) : (
          <span className="badge badge-ok">
            <span className="bdot" />
            All handled
          </span>
        )}
        <select
          className="select select-sm"
          style={{ minWidth: 160 }}
          value={replyCamp}
          onChange={(e) => setReplyCamp(e.target.value)}
        >
          <option value="">All campaigns</option>
          {campaigns.map((c) => (
            <option key={c.id}>{c.name}</option>
          ))}
        </select>
      </div>

      {replies.length === 0 ? (
        <div className="sum-empty">No replies yet. Inbound replies appear here as Smartlead reports them.</div>
      ) : (
        <div>
          {inView.map((r) => {
            const handled = !!r.handled_at;
            const sent = !!r.response_body;
            const meta = triageMeta(r.triage);
            const rowBusy = busy.has(r.id);
            const draft = drafts[r.id] ?? "";
            return (
              <div key={r.id} className={clsx("reply", handled && "done")}>
                <div className="reply-head">
                  <div className="av-sm">{nameInitials(r.prospect_name)}</div>
                  <div className="meta">
                    <div className="nm">{r.prospect_name || "Unnamed prospect"}</div>
                    <div className="ro">{r.prospect_role}</div>
                    <div className="tagline">
                      <span className="ttag">{r.campaign_name}</span>
                      {r.stage && <span className="ttag">{r.stage}</span>}
                    </div>
                  </div>
                  <span className={clsx("badge", meta?.badge ?? "badge-neutral")}>
                    <span className="bdot" />
                    {meta?.label ?? "Needs triage"}
                  </span>
                </div>

                <div className="reply-quote">
                  <div className="reply-qhead">
                    <span className="ql">Prospect replied</span>
                    <span className="reply-date">{fmtDate(r.occurred_at)}</span>
                  </div>
                  {r.subject && <div style={{ fontWeight: 600, marginBottom: 4 }}>{r.subject}</div>}
                  {r.reply_body || <span style={{ opacity: 0.6 }}>(no reply body captured)</span>}
                </div>

                {/* Triage — the human classification step (no auto-draft at MVP) */}
                {!r.triage && (
                  <div className="reply-triage" style={{ display: "flex", flexWrap: "wrap", gap: 8, marginBottom: 12 }}>
                    <span className="dl" style={{ marginRight: 4 }}>
                      Classify:
                    </span>
                    {TRIAGE_META.map((m) => (
                      <button
                        key={m.value}
                        type="button"
                        className="btn btn-ghost btn-sm"
                        disabled={rowBusy}
                        onClick={() => doTriage(r, m.value)}
                      >
                        {m.label}
                      </button>
                    ))}
                  </div>
                )}

                {/* Operator-authored threaded reply (→ Smartlead reply_to_thread) */}
                <div className="reply-draft">
                  <div className="dl">Your reply</div>
                  <textarea
                    value={sent ? r.response_body ?? "" : draft}
                    readOnly={sent}
                    placeholder="Write a threaded reply to send via Smartlead…"
                    onChange={(e) => setDraft(r.id, e.target.value)}
                  />
                  <div className="reply-actions" style={{ alignItems: "center", gap: 12 }}>
                    {!sent && (
                      <label
                        className="dl"
                        style={{ display: "flex", alignItems: "center", gap: 6, cursor: "pointer" }}
                      >
                        <input
                          type="checkbox"
                          checked={!!bookLink[r.id]}
                          onChange={(e) =>
                            setBookLink((s) => ({ ...s, [r.id]: e.target.checked }))
                          }
                        />
                        Include booking link
                      </label>
                    )}
                    <button
                      className="btn btn-accent btn-sm"
                      disabled={rowBusy || sent}
                      onClick={() => doRespond(r)}
                    >
                      {sent ? "Reply sent" : "Send Reply"}
                    </button>
                  </div>
                </div>

                <div className="reply-sent-banner">
                  <span>✓</span>
                  <span>{sent ? "Reply sent" : meta ? `Classified · ${meta.label}` : "Handled"}</span>
                </div>
              </div>
            );
          })}

          {replyCamp && inView.length === 0 && (
            <div className="sum-empty">No replies for {replyCamp} yet.</div>
          )}
        </div>
      )}

      <div className={clsx("queue-empty", inView.length > 0 && remainingInView === 0 && "show")}>
        <div className="ee">✓</div>
        <h3 style={{ fontSize: 20, color: "var(--ink)", marginBottom: 6 }}>Queue clear</h3>
        <p style={{ fontSize: 14 }}>
          Every reply in view has been handled. New replies will appear here as they&apos;re reported.
        </p>
      </div>
    </section>
  );
}

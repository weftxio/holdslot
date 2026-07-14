"use client";
import { useState } from "react";
import clsx from "clsx";
import { correctOutcome, setMeetingWon } from "@/lib/api";
import { useClient } from "@/lib/nav";
import { fmtDayYear } from "@/lib/dates";
import { Modal } from "@/components/Modal";
import { ConfirmFooter } from "@/components/workspace";
import { useToast } from "@/components/Toast";
import { useWorkspace } from "@/components/workspace/WorkspaceProvider";
import type { Recap } from "@/lib/workspace/types";
import { OUTCOME_BADGE as OUTCOME } from "@/lib/workspace/constants";

// M33 — the three states the owner can correct a held meeting to (mirrors the backend OutcomeIn).
const CORRECTABLE: { value: "qualified" | "short_call" | "noshow"; label: string }[] = [
  { value: "qualified", label: "Qualified" },
  { value: "short_call", label: "Short call" },
  { value: "noshow", label: "No-show" },
];

export default function SummariesPage() {
  // N47 — recaps come from the shared provider (not a static import) so a campaign rename remaps
  // their tag and they stay in this filter instead of orphaning under the old name.
  const { campaigns, recaps, reloadMeetings } = useWorkspace();
  const client = useClient();
  const toast = useToast();
  // M27 — filter by campaign_id, not name (same-named campaigns from different batches collide).
  const [sumCamp, setSumCamp] = useState("");
  const recapsInView = recaps.filter((rc) => !sumCamp || rc.campaignId === sumCamp);
  const sumCampName = campaigns.find((c) => c.id === sumCamp)?.name ?? "";

  // NF-3 — which recap's `won` flag is mid-save (disables its toggle). The `won`-only door writes the
  // deal outcome without touching any billing field, then reloadMeetings re-syncs the card.
  const [savingWon, setSavingWon] = useState<string | null>(null);
  // M28 — clicking the already-active button clears the flag back to undecided (null); the API's
  // `won` setter already accepts null, so the toggle is now three-state end to end.
  const onSetWon = async (id: string, won: boolean | null) => {
    setSavingWon(id);
    try {
      await setMeetingWon(client, id, won);
      await reloadMeetings();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not update the deal outcome", "warn");
    } finally {
      setSavingWon(null);
    }
  };

  // M33 — the outcome-correction / dispute door. Recaps are held (past) meetings, so the backend's
  // M18 guard never 409s here; correcting re-derives the amount/dispute-window before it bills, and
  // the "disputed" flag holds a qualified meeting out of billing (the client-dispute path).
  const [correctFor, setCorrectFor] = useState<Recap | null>(null);
  const [correctOc, setCorrectOc] = useState<"qualified" | "short_call" | "noshow">("qualified");
  const [correctDisputed, setCorrectDisputed] = useState(false);
  const [correcting, setCorrecting] = useState(false);
  const openCorrect = (rc: Recap) => {
    setCorrectOc((rc.outcome as "qualified" | "short_call" | "noshow") || "qualified");
    setCorrectDisputed(rc.disputed);
    setCorrectFor(rc);
  };
  const onCorrect = async () => {
    if (!correctFor || correcting) return;
    setCorrecting(true);
    try {
      await correctOutcome(client, correctFor.id, {
        outcome: correctOc,
        disputed: correctDisputed,
      });
      await reloadMeetings();
      toast("Outcome corrected");
      setCorrectFor(null);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Could not correct the outcome", "warn");
    } finally {
      setCorrecting(false);
    }
  };

  return (
    <section className="tabpane active">
      <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
        <div className="section-label" style={{ marginBottom: 0 }}>
          Meeting summaries, newest first
        </div>
        <select
          className="select select-sm"
          style={{ minWidth: 160 }}
          value={sumCamp}
          onChange={(e) => setSumCamp(e.target.value)}
        >
          <option value="">All campaigns</option>
          {campaigns.map((c) => (
            <option key={c.id} value={c.id}>
              {c.name}
            </option>
          ))}
        </select>
      </div>
      <div>
        {recapsInView.map((rc, sx) => {
          const oc = OUTCOME[rc.outcome || ""] || {
            label: rc.outcome || "—",
            badge: "badge-neutral",
          };
          return (
            <div className="sum-card" key={rc.id}>
              <div className="sum-tags">
                {rc.campaign && <span className="stag">{rc.campaign}</span>}
                {rc.batch && <span className="stag">{rc.batch}</span>}
              </div>
              <div className="sh">
                <div>
                  <div className="sm">
                    Meeting {sx + 1} · {rc.prospectName || "Prospect"}
                  </div>
                  <div className="smeta">
                    {fmtDayYear(rc.scheduledAt)} · {rc.companyName || "—"}
                  </div>
                </div>
                <span className="row" style={{ gap: 8, alignItems: "center" }}>
                  <span className={clsx("badge", oc.badge)}>
                    <span className="bdot" />
                    {oc.label}
                  </span>
                  {rc.disputed && (
                    <span className="badge badge-danger">
                      <span className="bdot" />
                      Disputed
                    </span>
                  )}
                  <button
                    type="button"
                    className="btn btn-ghost btn-2xs"
                    onClick={() => openCorrect(rc)}
                  >
                    Correct outcome
                  </button>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Recording</span>
                <span className="sv">
                  <span className="mph">Pending</span> · captured after the call
                </span>
              </div>
              <div className="srow">
                <span className="sk">Attendees</span>
                <span className="sv">
                  <span className="mph">Pending</span>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Discussed</span>
                <span className="sv">
                  <span className="mph">Pending</span> · a summary is prepared after the meeting.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Next step</span>
                <span className="sv">
                  <span className="mph">Pending</span>
                </span>
              </div>
              <div className="srow">
                <span className="sk">Feedback</span>
                <span className="sv">
                  {rc.rating ? `${rc.rating}/5` : <span className="mph">Awaiting</span>}
                </span>
              </div>
              <div className="srow">
                <span className="sk">Final conversion</span>
                <span className="sv">
                  <span className="row" style={{ gap: 8, alignItems: "center", flexWrap: "wrap" }}>
                    <button
                      type="button"
                      className={clsx("btn btn-2xs", rc.won === true ? "btn-accent" : "btn-ghost")}
                      aria-pressed={rc.won === true}
                      disabled={savingWon === rc.id}
                      onClick={() => void onSetWon(rc.id, rc.won === true ? null : true)}
                    >
                      Deal won
                    </button>
                    <button
                      type="button"
                      className={clsx("btn btn-2xs", rc.won === false ? "btn-danger" : "btn-ghost")}
                      aria-pressed={rc.won === false}
                      disabled={savingWon === rc.id}
                      onClick={() => void onSetWon(rc.id, rc.won === false ? null : false)}
                    >
                      No deal
                    </button>
                    {rc.won == null && <span className="mph">Not set</span>}
                  </span>
                </span>
              </div>
            </div>
          );
        })}
        {recapsInView.length === 0 && (
          <div className="sum-empty">
            No meeting recaps {sumCamp ? `for ${sumCampName}` : "yet"}.
          </div>
        )}
      </div>

      {/* M33 — owner outcome-correction / dispute door (backend: POST /meetings/{id}/outcome). */}
      <Modal
        open={correctFor !== null}
        onClose={() => !correcting && setCorrectFor(null)}
        title="Correct the meeting outcome"
        subtitle={
          correctFor
            ? `${correctFor.prospectName || "Prospect"} · ${fmtDayYear(correctFor.scheduledAt)}`
            : undefined
        }
        footer={
          <ConfirmFooter
            onCancel={() => setCorrectFor(null)}
            onConfirm={() => void onCorrect()}
            busy={correcting}
            variant="accent"
            busyLabel="Saving…"
            confirmLabel="Save correction"
          />
        }
      >
        {correctFor && (
          <>
            <p style={{ margin: "0 0 14px", lineHeight: 1.5 }}>
              Re-classify this meeting if the automatic outcome is wrong. Marking it{" "}
              <b>Qualified</b> re-derives the billable amount and the 48-hour dispute window;
              anything else clears the amount. This is the correction door — the deal-won flag is
              separate.
            </p>
            <div className="field" style={{ margin: 0 }}>
              <label>Outcome</label>
              <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
                {CORRECTABLE.map((o) => (
                  <button
                    key={o.value}
                    type="button"
                    className={clsx(
                      "btn btn-sm",
                      correctOc === o.value ? "btn-accent" : "btn-ghost"
                    )}
                    aria-pressed={correctOc === o.value}
                    onClick={() => setCorrectOc(o.value)}
                  >
                    {o.label}
                  </button>
                ))}
              </div>
            </div>
            <label
              className="dl"
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                marginTop: 16,
                cursor: "pointer",
              }}
            >
              <input
                type="checkbox"
                checked={correctDisputed}
                onChange={(e) => setCorrectDisputed(e.target.checked)}
              />
              Mark as disputed by the client (holds it out of billing while open)
            </label>
          </>
        )}
      </Modal>
    </section>
  );
}

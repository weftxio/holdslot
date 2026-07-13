"use client";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { useToast } from "@/components/Toast";
import { listBookings, respondReply, type BookingRowApi } from "@/lib/api";

const BADGE: Record<string, string> = {
  Confirmed: "badge-ok",
  "Awaiting confirm": "badge-warn",
  Expired: "badge-danger",
};

function fmt(iso: string | null): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

export default function BookingPage() {
  const client = useParams<{ client: string }>().client;
  const toast = useToast();
  const [rows, setRows] = useState<BookingRowApi[] | null>(null);
  const [propose, setPropose] = useState<{ id: string; eventId: string | null; msg: string } | null>(
    null
  );
  const [busy, setBusy] = useState(false);

  const load = useCallback(() => {
    listBookings(client).then(setRows).catch(() => setRows([]));
  }, [client]);
  useEffect(() => load(), [load]);

  const openPropose = (r: BookingRowApi) =>
    setPropose({
      id: r.id,
      eventId: r.reply_event_id,
      msg:
        `Hi ${r.prospect_name || "there"}, your earlier booking link expired before we could lock a time. ` +
        `Here's a fresh link for your call with HoldSlot — pick a time and it lands on both calendars: {{booking_link}}`,
    });

  async function sendNewInvite() {
    if (!propose || busy) return;
    if (!propose.eventId) {
      toast("No reply thread to resend into for this lead", "warn");
      return;
    }
    setBusy(true);
    try {
      await respondReply(client, propose.eventId, propose.msg, { includeBookingLink: true });
      setPropose(null);
      toast("New booking link sent");
      load();
    } catch {
      // M31 — a failure toast must render as a warning (was defaulting to the green "ok" kind); the
      // separator is a middot, per the house style.
      toast("Could not send · retry after a sync", "warn");
    } finally {
      setBusy(false);
    }
  }

  const list = rows ?? [];
  const confirmed = list.filter((r) => r.status === "Confirmed").length;
  const expired = list.filter((r) => r.status === "Expired").length;

  return (
    <section className="es-section active">
      <div className="es-summary">
        <div className="esc">
          <div className="ecap">Invites sent</div>
          <div className="en">{list.length}</div>
        </div>
        <div className="esc accent">
          <div className="ecap">Meetings accepted</div>
          <div className="en">{confirmed}</div>
        </div>
        <div className="esc">
          <div className="ecap">Expired unused</div>
          <div className="en">{expired}</div>
        </div>
      </div>
      <div className="panel">
        <div className="panel-head">
          <div>
            <h3>Status log</h3>
            <div className="ph-sub">
              Each prospect&apos;s suggested meeting time, the status, and the invitation email under
              every row
            </div>
          </div>
        </div>
        <div className="panel-pad">
          <div>
            {rows === null && <div className="ph" style={{ padding: "18px 4px" }}>Loading…</div>}
            {rows !== null && list.length === 0 && (
              <div className="ph" style={{ padding: "18px 4px" }}>
                No booking links sent yet. Send one from a reply in the Workspace.
              </div>
            )}
            {list.map((r, i) => (
              <div className="bk-card" key={r.id}>
                <div className="bk-top">
                  <div className="bk-ico">P{i + 1}</div>
                  <div className="bk-main">
                    <div className="bn">{r.prospect_name || "Prospect"}</div>
                    <div className="bm">
                      {[r.company_name, r.campaign_name].filter(Boolean).join(" · ")} · invite sent{" "}
                      {fmt(r.sent_at)}
                    </div>
                  </div>
                  <div className="bk-date">
                    <span className="bk-date-k">Link expires</span>
                    <span className="bk-date-v">{fmt(r.expires_at)}</span>
                  </div>
                  <span className={clsx("badge", BADGE[r.status] || "badge-neutral")}>
                    <span className="bdot" />
                    {r.status}
                  </span>
                  {r.status === "Expired" && propose?.id !== r.id && (
                    <button className="btn btn-accent btn-sm" onClick={() => openPropose(r)}>
                      Propose new time
                    </button>
                  )}
                </div>
                {r.status === "Expired" && propose?.id === r.id && (
                  <div className="bk-propose">
                    <div className="bk-invite-label">Send a fresh booking link</div>
                    <textarea
                      className="textarea"
                      style={{ marginTop: 10 }}
                      value={propose.msg}
                      onChange={(e) => setPropose({ ...propose, msg: e.target.value })}
                    />
                    <div className="row" style={{ marginTop: 10, justifyContent: "flex-end" }}>
                      <button className="btn btn-ghost btn-sm" onClick={() => setPropose(null)}>
                        Cancel
                      </button>
                      <button className="btn btn-accent btn-sm" onClick={sendNewInvite} disabled={busy}>
                        {busy ? "Sending…" : "Send new invite"}
                      </button>
                    </div>
                  </div>
                )}
                {r.invitation_preview && (
                  <div className="bk-invite">
                    <div className="bk-invite-label">Invitation email sent</div>
                    <div className="tmpl-mail">
                      <div className="tmpl-body">
                        <p>{r.invitation_preview}</p>
                      </div>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}

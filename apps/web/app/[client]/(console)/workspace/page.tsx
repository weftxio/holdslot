"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import "./workspace.css";

type IcpFields = {
  industry: string;
  companySize: string;
  revenue: string;
  regions: string;
  titles: string;
  seniority: string;
  departments: string;
  triggers: string;
  tech: string;
  geoAvoid: string;
  exclusions: string;
  disqualifiers: string;
};
type Icp = { short: string; tag: string; persona: string; fields: IcpFields };
type Batch = {
  name: string;
  count: number;
  approved: number;
  icp: string;
  status: "Approved" | "Pending" | "Rejected";
};
type Campaign = { name: string; batch: string };
type Row = {
  id: number;
  fit: "Strong" | "Good";
  batch: string;
  status: "Ready" | "New" | "Needs review";
  icp: string;
  checked: boolean;
};
type Reply = {
  n: string;
  role: string;
  campaign: string;
  batch: string;
  cls: string;
  badge: string;
  quote: string;
  draft: string;
  done?: string;
  neutral?: boolean;
  editing?: boolean;
  text: string;
};

const TABS = [
  ["brief", "Business brief"],
  ["list", "Prospect list"],
  ["batches", "Sendout Batch"],
  ["campaign", "Campaign"],
  ["replies", "Reply queue"],
  ["billing", "Billing ledger"],
  ["summaries", "Meeting summaries"],
] as const;

const FIT_CLS: Record<string, string> = { Strong: "badge-ok", Good: "badge-info" };
const STATUS_CLS: Record<string, string> = {
  Ready: "badge-neutral",
  New: "badge-info",
  "Needs review": "badge-warn",
};
const BATCH_STATUS_CLS: Record<string, string> = {
  Approved: "badge-ok",
  Rejected: "badge-danger",
  Pending: "badge-warn",
};
const batchBadge = (b: string) => (b === "Unassigned" ? "badge-neutral" : "badge-info");

const SEED: Omit<Row, "id" | "checked">[] = [
  { fit: "Strong", batch: "Batch 3", status: "Ready", icp: "ICP A" },
  { fit: "Strong", batch: "Batch 3", status: "Ready", icp: "ICP A" },
  { fit: "Good", batch: "Batch 3", status: "New", icp: "ICP B" },
  { fit: "Strong", batch: "Unassigned", status: "New", icp: "ICP A" },
  { fit: "Good", batch: "Unassigned", status: "Needs review", icp: "ICP B" },
  { fit: "Good", batch: "Batch 3", status: "Ready", icp: "ICP A" },
  { fit: "Strong", batch: "Unassigned", status: "Ready", icp: "ICP B" },
  { fit: "Good", batch: "Unassigned", status: "New", icp: "ICP A" },
  { fit: "Strong", batch: "Batch 3", status: "Ready", icp: "ICP B" },
  { fit: "Good", batch: "Unassigned", status: "Needs review", icp: "ICP A" },
];

const LEDGER: [string, string, string, string, string][] = [
  ["Qualified", "badge-ok", "Received", "Billed", "badge-ok"],
  ["Qualified", "badge-ok", "Received", "Billed", "badge-ok"],
  ["No-show", "badge-neutral", "None", "Not billable", "badge-neutral"],
  ["Qualified", "badge-ok", "Pending", "Held", "badge-warn"],
  ["Short call", "badge-neutral", "Received", "Not billable", "badge-neutral"],
];

const INITIAL_REPLIES: Reply[] = [
  {
    n: "Reply 1",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    cls: "Positive, wants a call",
    badge: "badge-ok",
    quote:
      "Placeholder positive reply. The prospect expresses interest and asks about availability next week.",
    draft:
      "Hi {{first_name}}, great to hear from you. I have a couple of windows next week. Here is a link to grab whichever suits: {{booking_link}}. Looking forward to it.",
    text: "",
  },
  {
    n: "Reply 2",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    cls: "Objection: timing",
    badge: "badge-warn",
    quote:
      "Placeholder objection reply. The prospect is interested but says the timing is wrong this quarter.",
    draft:
      "Hi {{first_name}}, completely understand that timing matters. Would it help if I followed up at the start of next quarter? In the meantime here is a one-pager to keep us on your radar.",
    text: "",
  },
  {
    n: "Reply 3",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    cls: "Referral: wrong person",
    badge: "badge-info",
    quote:
      "Placeholder referral reply. The prospect says they are not the right contact and names a colleague.",
    draft:
      "Hi {{first_name}}, thanks for pointing me in the right direction. I will reach out to {{referred_name}} and keep it brief.",
    text: "",
  },
].map((r) => ({ ...r, text: r.draft }));

const ICP_FIELD_DEFS: [keyof IcpFields, string][] = [
  ["industry", "Industry / segment"],
  ["companySize", "Company size"],
  ["revenue", "Revenue band"],
  ["regions", "Regions / markets"],
  ["titles", "Target titles"],
  ["seniority", "Seniority"],
  ["departments", "Departments"],
  ["triggers", "Buying triggers"],
  ["tech", "Tech / stack signals"],
  ["geoAvoid", "Geographies to avoid"],
  ["exclusions", "Exclusions"],
  ["disqualifiers", "Disqualifiers"],
];

const blankFields = (): IcpFields => ({
  industry: "",
  companySize: "",
  revenue: "",
  regions: "",
  titles: "",
  seniority: "",
  departments: "",
  triggers: "",
  tech: "",
  geoAvoid: "",
  exclusions: "",
  disqualifiers: "",
});

const sampleFields = (): IcpFields => ({
  industry: "SaaS, Fintech",
  companySize: "50–500 employees",
  revenue: "$10M–$100M ARR",
  regions: "North America, UK",
  titles: "Head of Sales, VP Revenue",
  seniority: "Director and above",
  departments: "Sales, RevOps",
  triggers: "Hiring SDRs, recent funding",
  tech: "Salesforce, Outreach",
  geoAvoid: "Sanctioned regions",
  exclusions: "Competitors, existing customers",
  disqualifiers: "Pre-revenue, <10 staff",
});

function Variants() {
  const v = (tag: string, body: React.ReactNode, win?: boolean) => (
    <div className={clsx("variant", win && "win")}>
      <div className="variant-head">
        <div className="vt">
          <span className="vtag">{tag}</span>Variant {tag}
          {win && (
            <span className="badge badge-ok" style={{ marginLeft: 4 }}>
              <span className="bdot" />
              Leading
            </span>
          )}
        </div>
        <div className="variant-stats">
          <div className="vs">
            <b>
              <Sample>n</Sample>%
            </b>
            Open
          </div>
          <div className="vs">
            <b>
              <Sample>n</Sample>%
            </b>
            Reply
          </div>
        </div>
      </div>
      <div className="variant-body">{body}</div>
    </div>
  );
  return (
    <>
      {v(
        "A",
        <>
          Hi <span className="mph">{"{{first_name}}"}</span>, a placeholder opening line about the
          current context at <span className="mph">{"{{company}}"}</span>. Placeholder one-sentence
          value proposition tied to a likely pain point. Placeholder soft ask for a short call.
          <br />
          <span className="mph">{"{{sender}}"}</span>
        </>,
        true
      )}
      {v(
        "B",
        <>
          Hi <span className="mph">{"{{first_name}}"}</span>, a placeholder pattern-interrupt
          opener. Placeholder proof point with a concrete number. Placeholder direct ask for{" "}
          <span className="mph">{"{{time_window}}"}</span>.<br />
          <span className="mph">{"{{sender}}"}</span>
        </>
      )}
      {v(
        "C",
        <>
          Hi <span className="mph">{"{{first_name}}"}</span>, a placeholder question-led opener
          about <span className="mph">{"{{industry}}"}</span>. Placeholder mutual-connection or
          trigger-event line. Placeholder low-friction ask.
          <br />
          <span className="mph">{"{{sender}}"}</span>
        </>
      )}
    </>
  );
}

function Seg({
  value,
  options,
  onChange,
}: {
  value: string;
  options: string[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="seg">
      {options.map((o) => (
        <button key={o} className={clsx(value === o && "on")} onClick={() => onChange(o)}>
          {o}
        </button>
      ))}
    </div>
  );
}

export default function Workspace() {
  const { client } = useParams<{ client: string }>();
  const toast = useToast();

  // campaign send controls
  const [sending, setSending] = useState("On");
  const [dailyCap, setDailyCap] = useState("50");
  const [split, setSplit] = useState("Even");

  const [tab, setTab] = useState<string>("brief");
  useEffect(() => {
    const h = location.hash.slice(1);
    if (TABS.some(([k]) => k === h)) setTab(h);
  }, []);
  function activate(name: string) {
    setTab(name);
    history.replaceState(null, "", "#" + name);
  }

  // ICPs
  const [icps, setIcps] = useState<Icp[]>([
    {
      short: "ICP A",
      tag: "Primary persona",
      persona: "Placeholder: the primary buyer we target, their role, and why they buy.",
      fields: sampleFields(),
    },
    {
      short: "ICP B",
      tag: "Expansion segment",
      persona: "Placeholder: a secondary segment to expand into once the primary lands.",
      fields: sampleFields(),
    },
  ]);
  const [icpSel, setIcpSel] = useState(0);
  function newIcp() {
    const letter = String.fromCharCode(65 + icps.length);
    setIcps((s) => [
      ...s,
      {
        short: "ICP " + letter,
        tag: "New profile",
        persona: "",
        fields: blankFields(),
      },
    ]);
    setIcpSel(icps.length);
    toast("ICP " + letter + " created");
  }
  function delIcp() {
    if (icps.length <= 1) return toast("Keep at least one ICP", "warn");
    const nm = icps[icpSel].short;
    const next = icps.filter((_, i) => i !== icpSel);
    setIcps(next);
    setIcpSel((s) => Math.min(s, next.length - 1));
    toast(nm + " deleted", "warn");
  }
  const updateIcp = (patch: Partial<Icp>) =>
    setIcps((s) => s.map((x, i) => (i === icpSel ? { ...x, ...patch } : x)));
  const updateIcpField = (key: keyof IcpFields, val: string) =>
    setIcps((s) => s.map((x, i) => (i === icpSel ? { ...x, fields: { ...x.fields, [key]: val } } : x)));
  const saveIcp = () => toast(icps[icpSel].short + " saved");

  // Batches / campaigns
  const [batches, setBatches] = useState<Batch[]>([
    { name: "Batch 1", count: 40, approved: 40, icp: "ICP A", status: "Approved" },
    { name: "Batch 2", count: 52, approved: 52, icp: "ICP A", status: "Approved" },
    { name: "Batch 3", count: 48, approved: 0, icp: "ICP B", status: "Pending" },
  ]);
  const [campaigns, setCampaigns] = useState<Campaign[]>([
    { name: "Campaign 1", batch: "Batch 3" },
  ]);

  // Prospect list
  const [rows, setRows] = useState<Row[]>(() =>
    SEED.map((d, i) => ({ ...d, id: i + 1, checked: false }))
  );
  const [nextId, setNextId] = useState(SEED.length + 1);
  const [search, setSearch] = useState("");
  const [fBatch, setFBatch] = useState("");
  const [fFit, setFFit] = useState("");
  const [fStatus, setFStatus] = useState("");
  const [researchIcp, setResearchIcp] = useState("ICP A");
  const [newBatchName, setNewBatchName] = useState("");

  const visible = useMemo(
    () =>
      rows.filter((r) => {
        const text = `prospect ${r.id} sample co ${r.id}`;
        return (
          (!search || text.includes(search.toLowerCase())) &&
          (!fBatch || r.batch === fBatch) &&
          (!fFit || r.fit === fFit) &&
          (!fStatus || r.status === fStatus)
        );
      }),
    [rows, search, fBatch, fFit, fStatus]
  );
  const selCount = visible.filter((r) => r.checked).length;
  const allChecked = visible.length > 0 && selCount === visible.length;

  function toggleRow(id: number) {
    setRows((s) => s.map((r) => (r.id === id ? { ...r, checked: !r.checked } : r)));
  }
  function toggleAll(on: boolean) {
    const ids = new Set(visible.map((r) => r.id));
    setRows((s) => s.map((r) => (ids.has(r.id) ? { ...r, checked: on } : r)));
  }
  function research() {
    const fits: Row["fit"][] = ["Strong", "Good", "Good", "Strong", "Good", "Strong"];
    const added: Row[] = fits.map((fit, k) => ({
      id: nextId + k,
      fit,
      batch: "Unassigned",
      status: "New",
      icp: researchIcp,
      checked: false,
    }));
    setRows((s) => [...added, ...s]);
    setNextId((n) => n + 6);
    toast("Researched 6 prospects from " + researchIcp);
  }
  function createBatch() {
    const name = newBatchName.trim() || "Batch " + (batches.length + 1);
    const picked = visible.filter((r) => r.checked);
    if (!picked.length) return toast("Select at least one prospect first", "warn");
    const ids = new Set(picked.map((r) => r.id));
    setRows((s) => s.map((r) => (ids.has(r.id) ? { ...r, batch: name } : r)));
    const icpSet = new Set(picked.map((r) => r.icp));
    setBatches((s) => [
      ...s,
      {
        name,
        count: picked.length,
        approved: 0,
        icp: icpSet.size === 1 ? [...icpSet][0] : "Multiple ICPs",
        status: "Pending",
      },
    ]);
    setNewBatchName("");
    toast(name + " created with " + picked.length + " prospects, pending client approval");
  }

  // Replies
  const [replies, setReplies] = useState<Reply[]>(INITIAL_REPLIES);
  const [replyCamp, setReplyCamp] = useState("");
  const remaining = replies.filter((r) => !r.done).length;
  function finishReply(i: number, label: string, neutral: boolean) {
    setReplies((s) =>
      s.map((r, idx) => (idx === i && !r.done ? { ...r, done: label, neutral } : r))
    );
  }
  function toggleEdit(i: number) {
    setReplies((s) =>
      s.map((r, idx) => {
        if (idx !== i) return r;
        if (r.editing) toast("Draft updated");
        return { ...r, editing: !r.editing };
      })
    );
  }

  const [sumCamp, setSumCamp] = useState("");
  const pendingBatches = batches.filter((b) => b.status === "Pending").length;

  return (
    <>
      <div className="page-head">
        <div>
          <h1>Workspace</h1>
        </div>
      </div>

      <div className="tabs ws-tabs" role="tablist">
        {TABS.map(([k, label]) => (
          <button
            key={k}
            className={clsx("tab", tab === k && "active")}
            onClick={() => activate(k)}
          >
            {label}
            {k === "batches" && <span className="cnt">{batches.length}</span>}
            {k === "campaign" && <span className="cnt">{campaigns.length}</span>}
            {k === "replies" && (
              <span className={clsx("cnt", remaining > 0 && "alert")}>{remaining}</span>
            )}
          </button>
        ))}
      </div>

      {/* BUSINESS BRIEF */}
      <section className={clsx("tabpane", tab === "brief" && "active")}>
        <div className="two-col">
          <div className="panel">
            <div className="panel-head">
              <div>
                <h3>Business brief</h3>
                <div className="ph-sub">What you sell and how we should position it</div>
              </div>
              <span className="badge badge-warn">
                <span className="bdot" />1 field to finish
              </span>
            </div>
            <div className="panel-pad">
              <div className="grid2">
                <div className="field">
                  <label>Company</label>
                  <input className="input" value="Northwind (sample)" readOnly />
                </div>
                <div className="field">
                  <label>Website</label>
                  <input className="input" value="northwind.example (placeholder)" readOnly />
                </div>
              </div>
              <div className="field">
                <label>
                  What you sell <span className="opt">· one line</span>
                </label>
                <input className="input" value="Placeholder: one-line value proposition" readOnly />
              </div>
              <div className="field">
                <label>Primary problem you solve</label>
                <input
                  className="input"
                  value="Placeholder: the pain you remove for buyers"
                  readOnly
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <label>
                  Proof &amp; positioning <span className="opt">· optional, not yet provided</span>
                </label>
                <textarea
                  className="textarea"
                  placeholder="Case studies, metrics, and differentiators the client wants us to lead with."
                />
              </div>
            </div>
          </div>

          <div className="panel">
            <div className="panel-head">
              <h3>Completeness</h3>
            </div>
            <div className="panel-pad">
              <div className="meter">
                <div className="ring" style={{ "--p": 88 } as React.CSSProperties}>
                  <span className="v">
                    88<small>%</small>
                  </span>
                </div>
                <div className="ml">
                  <b>Nearly ready.</b> One optional field is left before this brief is complete.
                </div>
              </div>
              <ul className="checklist">
                <li>
                  <span className="ck done">✓</span>
                  <span>Company &amp; offer</span>
                </li>
                <li>
                  <span className="ck done">✓</span>
                  <span>Ideal customer profiles</span>
                </li>
                <li>
                  <span className="ck done">✓</span>
                  <span>Titles &amp; geographies</span>
                </li>
                <li>
                  <span className="ck done">✓</span>
                  <span>Exclusion rules</span>
                </li>
                <li>
                  <span className="ck todo">○</span>
                  <span className="todo-t">
                    Proof &amp; positioning <Sample>optional</Sample>
                  </span>
                </li>
              </ul>
              <div className="comp-foot">Updates live as the client completes the intake.</div>
            </div>
          </div>
        </div>

        <div className="panel" style={{ marginTop: 22 }}>
          <div className="panel-head">
            <div>
              <h3>Ideal Customer Profiles</h3>
              <div className="ph-sub">
                Create and review the targeting profiles that drive sourcing
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={newIcp}>
              ＋ New ICP
            </button>
          </div>
          <div className="panel-pad">
            <div className="icp-tabs">
              {icps.map((p, i) => (
                <button
                  key={p.short}
                  className={clsx("icp-pill", i === icpSel && "on")}
                  onClick={() => setIcpSel(i)}
                >
                  <div className="ipn">{p.short}</div>
                  <div className="ipt">{p.tag}</div>
                </button>
              ))}
            </div>
            <div>
              <div className="icp-persona">
                <div className="ip-ico">◑</div>
                <div style={{ flex: 1 }}>
                  <div className="ip-t">Profile</div>
                  <div className="grid2">
                    <div className="field" style={{ marginBottom: 12 }}>
                      <label>ICP name</label>
                      <input
                        className="input"
                        value={icps[icpSel].short}
                        placeholder="e.g. ICP A"
                        onChange={(e) => updateIcp({ short: e.target.value })}
                      />
                    </div>
                    <div className="field" style={{ marginBottom: 12 }}>
                      <label>Segment label</label>
                      <input
                        className="input"
                        value={icps[icpSel].tag}
                        placeholder="e.g. Primary persona"
                        onChange={(e) => updateIcp({ tag: e.target.value })}
                      />
                    </div>
                  </div>
                  <div className="field" style={{ marginBottom: 0 }}>
                    <label>Persona</label>
                    <textarea
                      className="textarea"
                      value={icps[icpSel].persona}
                      placeholder="Describe this buyer profile, their role, and why they buy."
                      onChange={(e) => updateIcp({ persona: e.target.value })}
                    />
                  </div>
                </div>
              </div>

              <div className="icp-grid">
                {ICP_FIELD_DEFS.map(([key, label]) => (
                  <div className="icp-cell" key={key}>
                    <div className="k">{label}</div>
                    <input
                      className="input"
                      style={{ padding: "8px 10px", fontSize: 13.5 }}
                      value={icps[icpSel].fields[key]}
                      placeholder={label}
                      onChange={(e) => updateIcpField(key, e.target.value)}
                    />
                  </div>
                ))}
              </div>

              <div className="icp-foot">
                <div className="est">
                  <b>
                    <Sample>n</Sample>
                  </b>
                  estimated matching accounts <Sample>sample</Sample> · refreshed placeholder date
                </div>
                <div className="row">
                  <button className="btn btn-danger btn-sm" onClick={delIcp}>
                    Delete
                  </button>
                  <button className="btn btn-accent btn-sm" onClick={saveIcp}>
                    Save changes <span className="arrow">→</span>
                  </button>
                </div>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* PROSPECT LIST */}
      <section className={clsx("tabpane", tab === "list" && "active")}>
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Prospect list review</h3>
              <div className="ph-sub">
                Research from an ICP, review the results, then batch the ones worth sending · all
                rows <Sample>sample</Sample>
              </div>
            </div>
            <div className="row">
              <select
                className="select"
                style={{ width: "auto", minWidth: 120, padding: "9px 12px", fontSize: 13.5 }}
                value={researchIcp}
                onChange={(e) => setResearchIcp(e.target.value)}
              >
                {icps.map((p) => (
                  <option key={p.short}>{p.short}</option>
                ))}
              </select>
              <button className="btn btn-accent btn-sm" onClick={research}>
                Research prospects from ICP <span className="arrow">→</span>
              </button>
            </div>
          </div>
          <div className="filter-row" style={{ borderBottom: "1px solid var(--line)" }}>
            <div className="search">
              <span className="si">⌕</span>
              <input
                className="input"
                type="text"
                placeholder="Search name or company"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
              />
            </div>
            <select className="select" value={fBatch} onChange={(e) => setFBatch(e.target.value)}>
              <option value="">All batches</option>
              <option value="Unassigned">Unassigned pool</option>
              {batches.map((b) => (
                <option key={b.name}>{b.name}</option>
              ))}
            </select>
            <select className="select" value={fFit} onChange={(e) => setFFit(e.target.value)}>
              <option value="">Any fit</option>
              <option value="Strong">Strong fit</option>
              <option value="Good">Good fit</option>
            </select>
            <select className="select" value={fStatus} onChange={(e) => setFStatus(e.target.value)}>
              <option value="">Any status</option>
              <option value="Ready">Ready</option>
              <option value="New">New</option>
              <option value="Needs review">Needs review</option>
            </select>
            <span className="fcount">
              <b>{visible.length}</b> shown · <b>{selCount}</b> selected
            </span>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th style={{ width: 34 }}>
                    <input
                      type="checkbox"
                      className="tbl-check"
                      checked={allChecked}
                      onChange={(e) => toggleAll(e.target.checked)}
                    />
                  </th>
                  <th>Prospect</th>
                  <th>Title</th>
                  <th>Company</th>
                  <th>Source ICP</th>
                  <th>Fit</th>
                  <th>Batch</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {visible.map((r) => (
                  <tr key={r.id}>
                    <td>
                      <input
                        type="checkbox"
                        className="tbl-check"
                        checked={r.checked}
                        onChange={() => toggleRow(r.id)}
                      />
                    </td>
                    <td>
                      <div className="who-cell">
                        <div className="av-sm">P{r.id}</div>
                        <div>
                          <div className="nm">
                            Prospect {r.id} <Sample>sample</Sample>
                          </div>
                          <div className="sub">placeholder@company.example</div>
                        </div>
                      </div>
                    </td>
                    <td className="muted">Placeholder title</td>
                    <td>Sample Co {r.id}</td>
                    <td className="muted">{r.icp}</td>
                    <td>
                      <span className={clsx("badge", FIT_CLS[r.fit])}>
                        <span className="bdot" />
                        {r.fit}
                      </span>
                    </td>
                    <td>
                      <span className={clsx("badge", batchBadge(r.batch))}>
                        <span className="bdot" />
                        {r.batch}
                      </span>
                    </td>
                    <td>
                      <span className={clsx("badge", STATUS_CLS[r.status])}>
                        <span className="bdot" />
                        {r.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="batch-row">
            <span className="br-label">
              <span className="nbi">＋</span>Create sendout batch from selection
            </span>
            <input
              className="input"
              type="text"
              placeholder="Name this batch (e.g. Batch 4)"
              value={newBatchName}
              onChange={(e) => setNewBatchName(e.target.value)}
            />
            <span className="sel-pill">{selCount} selected</span>
            <button
              className="btn btn-ghost btn-sm"
              onClick={() => toast("Removed from pool", "warn")}
            >
              Remove selected
            </button>
            <button className="btn btn-primary btn-sm" onClick={createBatch}>
              Create batch <span className="arrow">→</span>
            </button>
          </div>
        </div>
      </section>

      {/* SENDOUT BATCH */}
      <section className={clsx("tabpane", tab === "batches" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            Batches sent for client approval · status updates as the client responds
          </div>
          <span className="badge badge-warn">
            <span className="bdot" />
            {pendingBatches} pending approval
          </span>
        </div>
        <div className="sob">
          {batches.map((b, i) => (
            <div className="sob-card" key={b.name}>
              <div className="sob-ico">B{i + 1}</div>
              <div className="sob-main">
                <div className="sob-name">
                  {b.name} <Sample>sample</Sample>
                </div>
                <div className="sob-meta">
                  <b style={{ color: "var(--ink)" }}>{b.approved}</b> approved ·{" "}
                  <b style={{ color: "var(--ink)" }}>{b.count}</b> total prospects · sourced from{" "}
                  {b.icp}
                </div>
              </div>
              <span className={clsx("badge", BATCH_STATUS_CLS[b.status] || "badge-neutral")}>
                <span className="bdot" />
                {b.status}
              </span>
              <Link href={`/${client}/client-status#approval`} className="btn btn-ghost btn-xs">
                Client status ↗
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* CAMPAIGN */}
      <section className={clsx("tabpane", tab === "campaign" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 14 }}>
          <div>
            <div className="section-label" style={{ marginBottom: 6 }}>
              Outreach send controls
            </div>
            <div className="row" style={{ gap: 16, flexWrap: "wrap" }}>
              <div className="row" style={{ gap: 8 }}>
                <span className="muted" style={{ fontSize: 13 }}>
                  Sending
                </span>
                <Seg
                  value={sending}
                  options={["On", "Pause"]}
                  onChange={(v) => {
                    setSending(v);
                    toast("Sending " + (v === "On" ? "resumed" : "paused"));
                  }}
                />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <span className="muted" style={{ fontSize: 13 }}>
                  Daily cap
                </span>
                <Seg
                  value={dailyCap}
                  options={["30", "50", "80"]}
                  onChange={(v) => {
                    setDailyCap(v);
                    toast("Daily cap set to " + v);
                  }}
                />
              </div>
              <div className="row" style={{ gap: 8 }}>
                <span className="muted" style={{ fontSize: 13 }}>
                  Split
                </span>
                <Seg
                  value={split}
                  options={["Even", "Favor winner"]}
                  onChange={(v) => {
                    setSplit(v);
                    toast("Split: " + v);
                  }}
                />
              </div>
            </div>
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setCampaigns((s) => [
                ...s,
                { name: "Campaign " + (s.length + 1), batch: batches[0]?.name || "None" },
              ]);
              toast("Campaign " + (campaigns.length + 1) + " created");
            }}
          >
            ＋ New campaign
          </button>
        </div>
        <div>
          {campaigns.map((cp, ci) => (
            <div className="camp" key={ci}>
              <div className="camp-head">
                <div className="ct">
                  <span className="vtag">{ci + 1}</span>
                  {cp.name} <Sample>sample</Sample>
                </div>
                <div className="cmeta">
                  <span className="muted">Sendout batch</span>
                  <select
                    className="select"
                    style={{ width: "auto", minWidth: 118, padding: "8px 11px", fontSize: 13 }}
                    value={cp.batch}
                    onChange={(e) => {
                      const v = e.target.value;
                      setCampaigns((s) => s.map((c, i) => (i === ci ? { ...c, batch: v } : c)));
                      toast("Campaign linked to " + v);
                    }}
                  >
                    {batches.map((b) => (
                      <option key={b.name}>{b.name}</option>
                    ))}
                  </select>
                  <span className="badge badge-info">
                    <span className="bdot" />3 variants
                  </span>
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={() => toast(cp.name + " sent to " + cp.batch)}
                  >
                    Send campaign <span className="arrow">→</span>
                  </button>
                </div>
              </div>
              <div className="camp-body">
                <Variants />
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* REPLY QUEUE */}
      <section className={clsx("tabpane", tab === "replies" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
          <div className="row" style={{ gap: 10, flexWrap: "wrap" }}>
            <div className="row" style={{ gap: 8 }}>
              <span className="muted" style={{ fontSize: 13 }}>
                Campaign
              </span>
              <select
                className="select"
                style={{ width: "auto", minWidth: 140, padding: "9px 12px", fontSize: 13.5 }}
                value={replyCamp}
                onChange={(e) => setReplyCamp(e.target.value)}
              >
                <option value="">All campaigns</option>
                {campaigns.map((c) => (
                  <option key={c.name}>{c.name}</option>
                ))}
              </select>
            </div>
          </div>
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
        </div>
        <div>
          {replies.map((r, i) => (
            <div
              key={i}
              className={clsx("reply", r.done && "done")}
              style={{ display: !replyCamp || r.campaign === replyCamp ? undefined : "none" }}
            >
              <div className="reply-head">
                <div className="av-sm">R{i + 1}</div>
                <div className="meta">
                  <div className="nm">
                    {r.n} <Sample>sample</Sample>
                  </div>
                  <div className="ro">{r.role}</div>
                  <div className="tagline">
                    <span className="ttag">{r.campaign}</span>
                    <span className="ttag">{r.batch}</span>
                  </div>
                </div>
                <span className={clsx("badge", r.badge)}>
                  <span className="bdot" />
                  {r.cls}
                </span>
              </div>
              <div className="reply-quote">
                <span className="ql">Prospect replied</span>
                {r.quote}
              </div>
              <div className="reply-draft">
                <div className="dl">
                  Suggested reply <Sample>auto-draft</Sample>
                </div>
                <textarea
                  readOnly={!r.editing}
                  value={r.text}
                  onChange={(e) => {
                    const v = e.target.value;
                    setReplies((s) => s.map((x, idx) => (idx === i ? { ...x, text: v } : x)));
                  }}
                />
                <div className="reply-actions">
                  <button
                    className="btn btn-accent btn-sm"
                    onClick={() => {
                      finishReply(i, "Approved, reply sent", false);
                      toast("Reply approved and sent");
                    }}
                  >
                    Approve &amp; send <span className="arrow">→</span>
                  </button>
                  <button className="btn btn-ghost btn-sm" onClick={() => toggleEdit(i)}>
                    {r.editing ? "Done editing" : "Edit draft"}
                  </button>
                  <span className="spacer" />
                  <select
                    className="status-select"
                    value=""
                    onChange={(e) => {
                      if (!e.target.value) return;
                      finishReply(i, "Status set: " + e.target.value, true);
                      toast("Marked as: " + e.target.value);
                    }}
                  >
                    <option value="">Set status…</option>
                    <option>Follow-up scheduled</option>
                    <option>Waiting on prospect</option>
                    <option>Not interested</option>
                    <option>No action needed</option>
                  </select>
                </div>
              </div>
              <div
                className="reply-sent-banner"
                style={r.neutral ? { background: "#F1F3F6", color: "var(--ink-faint)" } : undefined}
              >
                <span>{r.neutral ? "•" : "✓"}</span>
                <span>{r.done}</span>
              </div>
            </div>
          ))}
        </div>
        <div className={clsx("queue-empty", remaining === 0 && "show")}>
          <div className="ee">✓</div>
          <h3 style={{ fontSize: 20, color: "var(--ink)", marginBottom: 6 }}>Queue clear</h3>
          <p style={{ fontSize: 14 }}>
            Every classified reply has been handled. New replies will appear here as they&apos;re
            sorted.
          </p>
        </div>
      </section>

      {/* BILLING LEDGER */}
      <section className={clsx("tabpane", tab === "billing" && "active")}>
        <div className="ledger-sum">
          <div className="ls">
            <div className="lcap">Meetings billed</div>
            <div className="ln">
              <Sample>n</Sample>
            </div>
          </div>
          <div className="ls">
            <div className="lcap">Current cycle due</div>
            <div className="ln">
              $<Sample>amt</Sample>
            </div>
          </div>
          <div className="ls accent">
            <div className="lcap">Per qualified meeting</div>
            <div className="ln">
              $<Sample>rate</Sample>
            </div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Billing ledger</h3>
              <div className="ph-sub">
                Only completed, qualified meetings are billable · all rows <Sample>sample</Sample>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={() => toast("Statement exported")}>
              Export statement
            </button>
          </div>
          <div style={{ overflowX: "auto" }}>
            <table className="tbl">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Meeting with</th>
                  <th>Campaign / Batch</th>
                  <th>Outcome</th>
                  <th>Feedback</th>
                  <th>Status</th>
                  <th style={{ textAlign: "right" }}>Amount</th>
                </tr>
              </thead>
              <tbody>
                {LEDGER.map((ou, i) => (
                  <tr key={i}>
                    <td className="muted">Placeholder date</td>
                    <td>
                      <div className="nm">
                        Prospect {i + 1} <Sample>sample</Sample>
                      </div>
                      <div className="sub">Sample Co {i + 1}</div>
                    </td>
                    <td>
                      <div className="sum-tags" style={{ margin: 0 }}>
                        <span className="stag">Campaign 1</span>
                        <span className="stag">Batch 3</span>
                      </div>
                    </td>
                    <td>
                      <span className={clsx("badge", ou[1])}>
                        <span className="bdot" />
                        {ou[0]}
                      </span>
                    </td>
                    <td className="muted">{ou[2]}</td>
                    <td>
                      <span className={clsx("badge", ou[4])}>
                        <span className="bdot" />
                        {ou[3]}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tnum">
                      {ou[3] === "Billed" ? (
                        <>
                          $<Sample>amt</Sample>
                        </>
                      ) : (
                        <span className="muted">·</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* MEETING SUMMARIES */}
      <section className={clsx("tabpane", tab === "summaries" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            Meeting summaries, newest first
          </div>
          <div className="row" style={{ gap: 8 }}>
            <span className="muted" style={{ fontSize: 13 }}>
              Campaign
            </span>
            <select
              className="select"
              style={{ width: "auto", minWidth: 140, padding: "9px 12px", fontSize: 13.5 }}
              value={sumCamp}
              onChange={(e) => setSumCamp(e.target.value)}
            >
              <option value="">All campaigns</option>
              {campaigns.map((c) => (
                <option key={c.name}>{c.name}</option>
              ))}
            </select>
          </div>
        </div>
        <div>
          {[0, 1, 2].map((sx) => (
            <div
              className="sum-card"
              key={sx}
              style={{ display: !sumCamp || sumCamp === "Campaign 1" ? undefined : "none" }}
            >
              <div className="sum-tags">
                <span className="stag">Campaign 1</span>
                <span className="stag">Batch 3</span>
              </div>
              <div className="sh">
                <div>
                  <div className="sm">
                    Meeting {sx + 1} · Prospect {sx + 1} <Sample>sample</Sample>
                  </div>
                  <div className="smeta">
                    Placeholder date · Sample Co {sx + 1} · recording on file
                  </div>
                </div>
                <span className="badge badge-ok">
                  <span className="bdot" />
                  Qualified
                </span>
              </div>
              <div className="srow">
                <span className="sk">Attendees</span>
                <span className="sv">Placeholder names and titles</span>
              </div>
              <div className="srow">
                <span className="sk">Discussed</span>
                <span className="sv">
                  Placeholder summary of the conversation, pain points, and current stack.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Next step</span>
                <span className="sv">
                  <span className="mph">Placeholder</span>: follow-up action and owner.
                </span>
              </div>
              <div className="srow">
                <span className="sk">Sentiment</span>
                <span className="sv">Placeholder: qualified, warm, evaluating.</span>
              </div>
            </div>
          ))}
        </div>
      </section>
    </>
  );
}

"use client";
import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { highlightBody } from "@/lib/tmpl";
import "./workspace.css";

// ICP (section 2) + Personas (section 3), held per profile
type IcpFields = {
  industries: string[];
  companySize: string;
  maturity: string;
  geographies: string[];
  technologies: string[];
  jobTitles: string[];
  seniority: string[];
  departments: string[];
  buyerVsChampion: string;
  avoidTitles: string[];
};
type Icp = { short: string; tag: string; persona: string; fields: IcpFields };
// Global brief sections (1, 4, 5, 6, 7) — filled once
type Brief = {
  companyName: string;
  website: string;
  sell: string;
  problem: string;
  dealSize: string;
  salesCycle: string;
  valueProps: string[];
  proofPoints: string;
  signals: string;
  objections: string;
  competitors: string;
  tone: string;
  languages: string[];
  languageOther: string;
  excludeCustomers: string;
  excludeDeals: string;
  doNotContact: string;
  compliance: string;
  meetingsLand: string;
  attendees: string;
  availability: string;
  channel: string;
  contact: string;
  approver: string;
  meetingsPerMonth: string;
  qualifiedDef: string;
  first90: string;
};
type Batch = {
  name: string;
  count: number;
  approved: number;
  icp: string;
  status: "Approved" | "Pending" | "Rejected";
  createdAt: string;
  sentAt?: string;
  approvedAt?: string;
};
type Campaign = { name: string; batch: string; status: "Live" | "Pending"; variants: string[] };
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
  repliedAt: string;
  cls: string;
  badge: string;
  quote: string;
  draft: string;
  done?: string;
  editing?: boolean;
  nudge?: boolean;
  text: string;
};

const TABS = [
  ["brief", "Client Brief"],
  ["list", "Prospect List"],
  ["batches", "Approval Batches"],
  ["campaign", "Outreach Campaigns"],
  ["replies", "Reply Queue"],
  ["billing", "Billing Ledger"],
  ["summaries", "Meeting Recaps"],
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

type LedgerRow = {
  outcome: string;
  outcomeBadge: string;
  feedback: string;
  billing: string;
  billingBadge: string;
};
const LEDGER: LedgerRow[] = [
  {
    outcome: "Qualified",
    outcomeBadge: "badge-ok",
    feedback: "Received",
    billing: "Billed",
    billingBadge: "badge-ok",
  },
  {
    outcome: "Qualified",
    outcomeBadge: "badge-ok",
    feedback: "Received",
    billing: "Billed",
    billingBadge: "badge-ok",
  },
  {
    outcome: "No-show",
    outcomeBadge: "badge-neutral",
    feedback: "None",
    billing: "Not billable",
    billingBadge: "badge-neutral",
  },
  {
    outcome: "Qualified",
    outcomeBadge: "badge-ok",
    feedback: "Pending",
    billing: "Held",
    billingBadge: "badge-warn",
  },
  {
    outcome: "Short call",
    outcomeBadge: "badge-neutral",
    feedback: "Received",
    billing: "Not billable",
    billingBadge: "badge-neutral",
  },
];

type Recap = { campaign: string; batch: string; recId: string; won: boolean };
const RECAPS: Recap[] = [
  { campaign: "Campaign 1", batch: "Batch 3", recId: "kfx-9d2a-bv1", won: true },
  { campaign: "Campaign 1", batch: "Batch 3", recId: "qmt-7r4c-zp8", won: false },
  { campaign: "Campaign 1", batch: "Batch 3", recId: "hla-2w6e-nk3", won: true },
];

// Per-mode copy for the reply card (inbound reply vs outbound follow-up nudge).
const NUDGE_COPY = {
  qhead: "No reply yet",
  datePrefix: "last outreach ",
  body: "Prospect hasn't responded yet — a follow-up nudge is drafted and ready to send.",
  draftLabel: "Suggested follow-up",
  cta: "Send Follow-Up",
  done: "Follow-up nudge sent",
};
const REPLY_COPY = {
  qhead: "Prospect replied",
  datePrefix: "",
  body: "",
  draftLabel: "Suggested reply",
  cta: "Send Reply",
  done: "Reply approved and sent",
};

const INITIAL_REPLIES: Reply[] = [
  {
    n: "Reply 1",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    repliedAt: "2026-06-02",
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
    repliedAt: "2026-05-30",
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
    repliedAt: "2026-05-28",
    cls: "Referral: wrong person",
    badge: "badge-info",
    quote:
      "Placeholder referral reply. The prospect says they are not the right contact and names a colleague.",
    draft:
      "Hi {{first_name}}, thanks for pointing me in the right direction. I will reach out to {{referred_name}} and keep it brief.",
    text: "",
  },
  // Follow-up nudges — prospects who haven't replied yet; a drafted nudge is ready to send.
  {
    n: "Reply 4",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    repliedAt: "2026-05-26",
    cls: "Follow-up nudge",
    badge: "badge-info",
    quote: "",
    draft:
      "Hi {{first_name}}, floating this back to the top of your inbox. {{value_prop_one_liner}} — worth a quick 15 minutes next week? Here is a link if it is easier: {{booking_link}}.",
    nudge: true,
    text: "",
  },
  {
    n: "Reply 5",
    role: "Placeholder title · Sample Co",
    campaign: "Campaign 1",
    batch: "Batch 3",
    repliedAt: "2026-05-24",
    cls: "Follow-up nudge",
    badge: "badge-info",
    quote: "",
    draft:
      "Hi {{first_name}}, last note from me on this — happy to share a short summary of how we have helped similar {{industry}} teams. Want me to send it over?",
    nudge: true,
    text: "",
  },
]
  .map((r) => ({ ...r, text: r.draft }))
  // Most-aged first: oldest outreach/reply date on top (ISO strings sort lexically).
  .sort((a, b) => a.repliedAt.localeCompare(b.repliedAt));

// reply dates relative to the app's current date (fixed for the mock)
const TODAY_ISO = "2026-06-03";
const REPLY_TODAY = new Date(TODAY_ISO + "T00:00:00Z");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
function fmtShortDate(iso: string) {
  const [, m, d] = iso.split("-").map(Number);
  return MONTHS[m - 1] + " " + d;
}
function daysAgoLabel(iso: string) {
  const diff = Math.round(
    (REPLY_TODAY.getTime() - new Date(iso + "T00:00:00Z").getTime()) / 86400000
  );
  return diff <= 0 ? "today" : diff === 1 ? "1 day ago" : diff + " days ago";
}

const SENIORITY_OPTS = ["C-level", "VP", "Director", "Manager", "Individual contributor"];
const LANGUAGE_OPTS = ["English", "Mandarin", "Spanish", "French", "German", "Other"];
const CYCLE_OPTS = ["Less than 1 month", "1–3 months", "3–6 months", "6+ months"];
const MATURITY_OPTS = ["Startup", "Growth", "SME", "Enterprise", "Any"];
const TONE_OPTS = ["Formal", "Professional & friendly", "Casual", "Let us recommend"];
const CHANNEL_OPTS = ["Slack", "WhatsApp", "Email", "Other"];

const blankFields = (): IcpFields => ({
  industries: [],
  companySize: "",
  maturity: "",
  geographies: [],
  technologies: [],
  jobTitles: [],
  seniority: [],
  departments: [],
  buyerVsChampion: "",
  avoidTitles: [],
});

const sampleFields = (): IcpFields => ({
  industries: ["SaaS", "Fintech"],
  companySize: "50–500 employees",
  maturity: "Growth",
  geographies: ["North America", "UK"],
  technologies: ["Salesforce", "Outreach"],
  jobTitles: ["Head of Sales", "VP Revenue"],
  seniority: ["VP", "Director"],
  departments: ["Sales", "RevOps"],
  buyerVsChampion: "CRO signs off, Head of Sales champions",
  avoidTitles: ["Procurement", "Junior analysts"],
});

const sampleBrief = (): Brief => ({
  companyName: "Northwind",
  website: "https://northwind.example",
  sell: "A workforce analytics platform that helps enterprises reduce attrition",
  problem:
    "Companies lose their best people without warning. We surface the early signals so leaders can act before resignations happen.",
  dealSize: "$25,000 / year",
  salesCycle: "1–3 months",
  valueProps: [
    "Predict attrition 90 days out",
    "Cut onboarding time 40%",
    "One view for every team lead",
  ],
  proofPoints:
    "Work with 3 of the top 10 logistics firms in the region · Cut onboarding time by 40% for a Fortune 500 client · Backed by a tier-1 investor.",
  signals:
    "Just hired a VP Sales · Recently expanded to a new market · Just raised funding · Posting about scaling the team.",
  objections: "We already have a tool · No budget this quarter",
  competitors: "Competitor A, Competitor B",
  tone: "Professional & friendly",
  languages: ["English"],
  languageOther: "",
  excludeCustomers: "",
  excludeDeals: "",
  doNotContact: "",
  compliance: "",
  meetingsLand: "Round-robin across 3 AEs",
  attendees: "Jane Doe (AE), John Smith (Sales Lead)",
  availability: "Tue–Thu, 10am–4pm GMT",
  channel: "Slack",
  contact: "Sample Contact, Ops · contact@northwind.example",
  approver: "Sample Approver, COO",
  meetingsPerMonth: "15",
  qualifiedDef:
    "A decision-maker at a company in our ICP who shows up to a 20-minute call and has genuine interest in solving the problem we address.",
  first90:
    "A predictable flow of 12–15 qualified meetings a month and at least 2 deals in late-stage pipeline.",
});

// type-and-enter chips for multi-value fields
function TagInput({
  value,
  onChange,
  placeholder,
  invalid,
}: {
  value: string[];
  onChange: (v: string[]) => void;
  placeholder?: string;
  invalid?: boolean;
}) {
  const [draft, setDraft] = useState("");
  const add = () => {
    const t = draft.trim();
    if (t && !value.includes(t)) onChange([...value, t]);
    setDraft("");
  };
  return (
    <div className={clsx("tag-input", invalid && "err")}>
      {value.map((t) => (
        <span className="tag-chip" key={t}>
          {t}
          <button
            type="button"
            className="tx"
            aria-label={"Remove " + t}
            onClick={() => onChange(value.filter((x) => x !== t))}
          >
            ×
          </button>
        </span>
      ))}
      <input
        className="tag-entry"
        value={draft}
        placeholder={value.length ? "" : placeholder}
        onChange={(e) => setDraft(e.target.value)}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === ",") {
            e.preventDefault();
            add();
          } else if (e.key === "Backspace" && !draft && value.length) {
            onChange(value.slice(0, -1));
          }
        }}
        onBlur={add}
      />
    </div>
  );
}

// fixed-option multi-select pills
function PillGroup({
  options,
  value,
  onChange,
  invalid,
}: {
  options: string[];
  value: string[];
  onChange: (v: string[]) => void;
  invalid?: boolean;
}) {
  const toggle = (o: string) =>
    onChange(value.includes(o) ? value.filter((x) => x !== o) : [...value, o]);
  return (
    <div className={clsx("brief-pills", invalid && "err")}>
      {options.map((o) => (
        <label key={o} className={clsx("brief-pill", value.includes(o) && "on")}>
          <input type="checkbox" checked={value.includes(o)} onChange={() => toggle(o)} />
          <span className="bx" />
          {o}
        </label>
      ))}
    </div>
  );
}

// label + required/optional badge + helper line
function Lbl({ children, req, help }: { children: React.ReactNode; req?: boolean; help?: string }) {
  return (
    <>
      <label>
        {children}
        <span className={req ? "brief-req" : "brief-opt"}>{req ? "Required" : "Optional"}</span>
      </label>
      {help && <div className="brief-help">{help}</div>}
    </>
  );
}

// collapsible brief section with a Complete / Pending status label
function Section({
  num,
  title,
  sub,
  complete,
  open,
  onToggle,
  onContinue,
  last,
  hideFoot,
  extra,
  children,
}: {
  num: number;
  title: string;
  sub: string;
  complete: boolean;
  open: boolean;
  onToggle: () => void;
  onContinue: () => void;
  last?: boolean;
  hideFoot?: boolean;
  extra?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className={clsx("panel brief-sec", open && "open")} id={"brief-sec-" + num}>
      <div
        className="brief-head"
        role="button"
        tabIndex={0}
        aria-expanded={open}
        onClick={onToggle}
        onKeyDown={(e) => {
          if (e.key === "Enter" || e.key === " ") {
            e.preventDefault();
            onToggle();
          }
        }}
      >
        <div className="brief-num">{num}</div>
        <div className="brief-htext">
          <h3>{title}</h3>
          <div className="ph-sub">{sub}</div>
        </div>
        <span className={clsx("badge", complete ? "badge-ok" : "badge-warn")}>
          <span className="bdot" />
          {complete ? "Complete" : "Pending"}
        </span>
        {extra}
        <span className="brief-chev" aria-hidden>
          ⌄
        </span>
      </div>
      {open && children}
      {open && !hideFoot && (
        <div className="brief-secfoot">
          <button className="btn btn-accent btn-sm" onClick={onContinue}>
            {last ? "Save draft" : "Save & continue"}
          </button>
        </div>
      )}
    </div>
  );
}

const DEFAULT_VARIANT_BODIES: Record<string, string> = {
  A: "Hi {{first_name}}, a placeholder opening line about the current context at {{company}}. Placeholder one-sentence value proposition tied to a likely pain point. Placeholder soft ask for a short call.\n{{sender}}",
  B: "Hi {{first_name}}, a placeholder pattern-interrupt opener. Placeholder proof point with a concrete number. Placeholder direct ask for {{time_window}}.\n{{sender}}",
  C: "Hi {{first_name}}, a placeholder question-led opener about {{industry}}. Placeholder mutual-connection or trigger-event line. Placeholder low-friction ask.\n{{sender}}",
};
const defaultBody = (tag: string) =>
  DEFAULT_VARIANT_BODIES[tag] ?? "Placeholder message body for variant " + tag + ".";
// Variant bodies are stored per campaign so editing one campaign's copy never
// changes another's. Key = "<campaignName>:<tag>" (name is stable across reorder/delete).
const bodyKey = (campName: string, tag: string) => campName + ":" + tag;

function Variants({
  tags,
  editable,
  campName,
  bodies,
  editKey,
  onRemove,
  onAdd,
  onEdit,
  onBody,
}: {
  tags: string[];
  editable: boolean;
  campName: string;
  bodies: Record<string, string>;
  editKey: string | null;
  onRemove: (tag: string) => void;
  onAdd: () => void;
  onEdit: (tag: string) => void;
  onBody: (tag: string, val: string) => void;
}) {
  return (
    <>
      {tags.map((tag, i) => {
        const key = bodyKey(campName, tag);
        const body = bodies[key] ?? defaultBody(tag);
        const editing = editKey === key;
        return (
          <div className={clsx("variant", i === 0 && "win")} key={tag}>
            <div className="variant-head">
              <div className="vt">
                <span className="vtag">{tag}</span>Variant {tag}
                {i === 0 && (
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
                {editable && (
                  <button
                    type="button"
                    className="btn btn-ghost btn-xs"
                    onClick={() => onEdit(tag)}
                  >
                    {editing ? "Done" : "Edit"}
                  </button>
                )}
                {editable && (
                  <button
                    type="button"
                    className="variant-rm"
                    aria-label={"Remove variant " + tag}
                    onClick={() => onRemove(tag)}
                  >
                    ×
                  </button>
                )}
              </div>
            </div>
            {editing ? (
              <textarea
                className="textarea variant-edit"
                value={body}
                onChange={(e) => onBody(tag, e.target.value)}
              />
            ) : (
              <div className="variant-body">{highlightBody(body)}</div>
            )}
          </div>
        );
      })}
      {editable && (
        <button type="button" className="variant-add" onClick={onAdd}>
          ＋ Add variant
        </button>
      )}
    </>
  );
}

export default function Workspace() {
  const { client } = useParams<{ client: string }>();
  const toast = useToast();

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
  const setIcpField = <K extends keyof IcpFields>(key: K, val: IcpFields[K]) =>
    setIcps((s) =>
      s.map((x, i) => (i === icpSel ? { ...x, fields: { ...x.fields, [key]: val } } : x))
    );

  // Business brief (global sections)
  const [brief, setBrief] = useState<Brief>(sampleBrief);
  const [submitted, setSubmitted] = useState(false);
  // CSV attachment name per exclusion field (keyed: "customers", "deals")
  const [csvNames, setCsvNames] = useState<Record<string, string>>({});
  const onCsv = (key: string) => (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    setCsvNames((s) => ({ ...s, [key]: file.name }));
    toast(file.name + " attached");
    e.target.value = "";
  };
  const setB = <K extends keyof Brief>(key: K, val: Brief[K]) =>
    setBrief((s) => ({ ...s, [key]: val }));
  const setValueProp = (i: number, val: string) =>
    setBrief((s) => {
      const next = [...s.valueProps];
      next[i] = val;
      return { ...s, valueProps: next };
    });
  const f = icps[icpSel].fields;

  // accordion: one section open at a time (0 = all collapsed)
  const [openSec, setOpenSec] = useState(1);
  // after a section opens, bring its title bar to the top (below the sticky bars)
  const scrollToSec = (n: number) =>
    setTimeout(
      () =>
        document
          .getElementById("brief-sec-" + n)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      60
    );
  const toggle = (n: number) => {
    const next = openSec === n ? 0 : n;
    setOpenSec(next);
    if (next) scrollToSec(next);
  };
  function saveAndContinue(cur: number) {
    // Surface missing required fields once the operator tries to save.
    setSubmitted(true);
    toast("Draft saved");
    const order = [1, 2, 3, 4, 5, 6];
    const next = order.find((n) => n > cur && !secComplete[n]) ?? (cur < 6 ? cur + 1 : cur);
    setOpenSec(next);
    if (next !== cur) scrollToSec(next);
  }

  const filled = (v: string | string[]) => (Array.isArray(v) ? v.length > 0 : v.trim() !== "");
  const icpReady = icps.every(
    (p) =>
      p.fields.industries.length &&
      p.fields.companySize.trim() &&
      p.fields.geographies.length &&
      p.fields.jobTitles.length &&
      p.fields.seniority.length &&
      p.fields.departments.length
  );
  // per-section completeness (drives the status label + the top bar)
  const secComplete: Record<number, boolean> = {
    1:
      filled(brief.companyName) &&
      filled(brief.website) &&
      filled(brief.sell) &&
      filled(brief.problem) &&
      filled(brief.dealSize) &&
      filled(brief.salesCycle),
    2: icpReady,
    3:
      brief.valueProps.some((v) => v.trim()) &&
      filled(brief.proofPoints) &&
      filled(brief.signals) &&
      filled(brief.tone) &&
      brief.languages.length > 0,
    4: filled(brief.excludeCustomers) && filled(brief.excludeDeals),
    5:
      filled(brief.meetingsLand) &&
      filled(brief.attendees) &&
      filled(brief.availability) &&
      filled(brief.channel) &&
      filled(brief.contact) &&
      filled(brief.approver),
    6: filled(brief.meetingsPerMonth) && filled(brief.qualifiedDef),
  };
  const completePct = Math.round((Object.values(secComplete).filter(Boolean).length / 6) * 100);
  const errCls = (ok: boolean, base = "input") => clsx(base, submitted && !ok && "err");

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
    { name: "Campaign 1", batch: "Batch 1", status: "Live", variants: ["A", "B", "C"] },
    { name: "Campaign 2", batch: "Batch 3", status: "Pending", variants: ["A", "B", "C"] },
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
  const [fIcp, setFIcp] = useState("");
  const [newBatchName, setNewBatchName] = useState("");

  const visible = useMemo(
    () =>
      rows.filter((r) => {
        const text = `prospect ${r.id} sample co ${r.id}`;
        return (
          (!search || text.includes(search.toLowerCase())) &&
          (!fIcp || r.icp === fIcp) &&
          (!fBatch || r.batch === fBatch) &&
          (!fFit || r.fit === fFit) &&
          (!fStatus || r.status === fStatus)
        );
      }),
    [rows, search, fIcp, fBatch, fFit, fStatus]
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
    const targetIcp = fIcp || icps[0]?.short || "ICP A";
    const fits: Row["fit"][] = ["Strong", "Good", "Good", "Strong", "Good", "Strong"];
    const added: Row[] = fits.map((fit, k) => ({
      id: nextId + k,
      fit,
      batch: "Unassigned",
      status: "New",
      icp: targetIcp,
      checked: false,
    }));
    setRows((s) => [...added, ...s]);
    setNextId((n) => n + 6);
    toast("Researched 6 prospects from " + targetIcp);
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
        createdAt: TODAY_ISO,
      },
    ]);
    setNewBatchName("");
    toast(name + " created with " + picked.length + " prospects, pending client approval");
  }

  // Replies
  const [replies, setReplies] = useState<Reply[]>(INITIAL_REPLIES);
  const [replyCamp, setReplyCamp] = useState("");
  const remaining = replies.filter((r) => !r.done).length; // global total, for the tab pip
  const inViewReplies = replies.filter((r) => !replyCamp || r.campaign === replyCamp);
  const remainingInView = inViewReplies.filter((r) => !r.done).length;
  function finishReply(i: number, label: string) {
    setReplies((s) => s.map((r, idx) => (idx === i && !r.done ? { ...r, done: label } : r)));
  }
  function toggleEdit(i: number) {
    const wasEditing = replies[i]?.editing;
    setReplies((s) => s.map((r, idx) => (idx === i ? { ...r, editing: !r.editing } : r)));
    if (wasEditing) toast("Draft updated");
  }

  const [sumCamp, setSumCamp] = useState("");
  const recapsInView = RECAPS.filter((rc) => !sumCamp || rc.campaign === sumCamp);
  const pendingBatches = batches.filter((b) => b.status === "Pending").length;

  function exportLedgerCsv() {
    const headers = [
      "Date",
      "Meeting with",
      "Company",
      "Campaign",
      "Batch",
      "Outcome",
      "Feedback",
      "Status",
      "Amount (HKD)",
    ];
    const rows = LEDGER.map((ou, i) => [
      "Placeholder date",
      "Prospect " + (i + 1),
      "Sample Co " + (i + 1),
      "Campaign 1",
      "Batch 3",
      ou.outcome,
      ou.feedback,
      ou.billing,
      ou.billing === "Billed" ? "4000" : "",
    ]);
    const csv = [headers, ...rows]
      .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(","))
      .join("\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "billing-ledger.csv";
    a.click();
    URL.revokeObjectURL(url);
    toast("CSV exported");
  }

  // expandable batch detail (sample prospect rows)
  const [openBatch, setOpenBatch] = useState<string | null>(null);
  const toggleBatch = (name: string, id: string, open: boolean) => {
    setOpenBatch(open ? null : name);
    if (!open) {
      setTimeout(
        () => document.getElementById(id)?.scrollIntoView({ behavior: "smooth", block: "start" }),
        60
      );
    }
  };

  // deep-link: ?batch=<name> opens the Approval Batches tab with that batch expanded
  useEffect(() => {
    const b = new URLSearchParams(location.search).get("batch");
    if (!b) return;
    setTab("batches");
    // Only expand/scroll when the requested batch actually exists — a stale or
    // unknown ?batch= value just lands on the tab instead of expanding nothing.
    const idx = batches.findIndex((x) => x.name === b);
    if (idx < 0) return;
    setOpenBatch(b);
    setTimeout(
      () =>
        document
          .getElementById("sob-item-" + idx)
          ?.scrollIntoView({ behavior: "smooth", block: "start" }),
      160
    );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // editable variant bodies, keyed per campaign ("<campName>:<tag>"); defaults come
  // from defaultBody() at render, so we only store edits here.
  const [variantBodies, setVariantBodies] = useState<Record<string, string>>({});
  const [editVar, setEditVar] = useState<string | null>(null);
  const editVariant = (campName: string, tag: string) => {
    const key = bodyKey(campName, tag);
    if (editVar === key) {
      setEditVar(null);
      toast("Variant " + tag + " saved");
    } else {
      setEditVar(key);
    }
  };
  const setVariantBody = (campName: string, tag: string, val: string) =>
    setVariantBodies((s) => ({ ...s, [bodyKey(campName, tag)]: val }));

  // batch approval action: send the approval email, or nudge if it was already sent
  const sendApproval = (name: string) => {
    const alreadySent = !!batches.find((x) => x.name === name)?.sentAt;
    setBatches((s) =>
      s.map((b) => (b.name === name ? { ...b, sentAt: b.sentAt || TODAY_ISO } : b))
    );
    toast(alreadySent ? "Follow-up nudge sent to client" : "Approval email sent to client");
  };

  // expandable campaigns (all collapsed by default)
  const [openCamp, setOpenCamp] = useState<number | null>(null);
  const removeVariant = (ci: number, tag: string) => {
    const c = campaigns[ci];
    if (!c) return;
    if (c.variants.length <= 1) return toast("Keep at least one variant", "warn");
    setCampaigns((s) =>
      s.map((x, i) => (i === ci ? { ...x, variants: x.variants.filter((t) => t !== tag) } : x))
    );
    toast("Variant " + tag + " removed", "warn");
  };
  const addVariant = (ci: number) => {
    const c = campaigns[ci];
    if (!c) return;
    let code = 65; // 'A'
    while (c.variants.includes(String.fromCharCode(code))) code++;
    const next = String.fromCharCode(code);
    setCampaigns((s) =>
      s.map((x, i) => (i === ci ? { ...x, variants: [...x.variants, next] } : x))
    );
    toast("Variant " + next + " added");
  };
  const toggleCamp = (ci: number, open: boolean) => {
    setOpenCamp(open ? null : ci);
    if (!open) {
      setTimeout(
        () =>
          document
            .getElementById("camp-" + ci)
            ?.scrollIntoView({ behavior: "smooth", block: "start" }),
        60
      );
    }
  };
  const deleteCampaign = (ci: number) => {
    const c = campaigns[ci];
    if (!c || c.status === "Live") return;
    setCampaigns((s) => s.filter((_, i) => i !== ci));
    setOpenCamp(null);
    toast(c.name + " deleted", "warn");
  };
  const batchProspects = (b: Batch) =>
    Array.from({ length: b.count }, (_, i) => ({
      name: "Prospect " + (i + 1),
      company: "Sample Co " + (i + 1),
      status: i < b.approved ? "Approved" : b.status === "Rejected" ? "Rejected" : "Pending",
    }));

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
        <div className="brief-top">
          <div className="brief-legend">
            <span>
              <span className="brief-req">Required</span> Needed before we start
            </span>
            <span>
              <span className="brief-opt">Optional</span> Helpful, not essential
            </span>
          </div>
          <div className="brief-progress">
            <div className="bp-bar">
              <div className="bp-fill" style={{ width: completePct + "%" }} />
            </div>
            <span className="bp-label">{completePct}% complete</span>
          </div>
        </div>

        {/* 1 · Company & Product Basics */}
        <Section
          num={1}
          title="Company & Product Basics"
          sub="Who you are and what you sell"
          complete={secComplete[1]}
          open={openSec === 1}
          onToggle={() => toggle(1)}
          onContinue={() => saveAndContinue(1)}
        >
          <div className="panel-pad">
            <div className="grid2">
              <div className="field">
                <Lbl req help="The brand name as it should appear in email signatures.">
                  Company name
                </Lbl>
                <input
                  className={errCls(filled(brief.companyName))}
                  value={brief.companyName}
                  placeholder="e.g. Acme Analytics"
                  onChange={(e) => setB("companyName", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl req help="Used for enrichment context and to verify what you sell.">
                  Website
                </Lbl>
                <input
                  type="url"
                  className={errCls(filled(brief.website))}
                  value={brief.website}
                  placeholder="https://"
                  onChange={(e) => setB("website", e.target.value)}
                />
              </div>
            </div>
            <div className="field">
              <Lbl
                req
                help="If you can't say it cleanly in one line, the campaign suffers. Keep it simple."
              >
                What do you sell, in one sentence?
              </Lbl>
              <input
                className={errCls(filled(brief.sell))}
                value={brief.sell}
                placeholder="e.g. A workforce analytics platform that reduces attrition"
                onChange={(e) => setB("sell", e.target.value)}
              />
            </div>
            <div className="field">
              <Lbl
                req
                help="Not the features, the underlying problem. This becomes the spine of every message."
              >
                What problem do you solve for your customers?
              </Lbl>
              <textarea
                className={errCls(filled(brief.problem), "textarea")}
                value={brief.problem}
                onChange={(e) => setB("problem", e.target.value)}
              />
            </div>
            <div className="grid2">
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl req help="Annual contract value. Determines whether the unit economics work.">
                  Average deal size (annual)
                </Lbl>
                <input
                  className={errCls(filled(brief.dealSize))}
                  value={brief.dealSize}
                  placeholder="e.g. $25,000 / year"
                  onChange={(e) => setB("dealSize", e.target.value)}
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl req help="Shapes follow-up cadence and time-to-revenue.">
                  Typical sales cycle length
                </Lbl>
                <select
                  className={errCls(filled(brief.salesCycle), "select")}
                  value={brief.salesCycle}
                  onChange={(e) => setB("salesCycle", e.target.value)}
                >
                  <option value="">Select…</option>
                  {CYCLE_OPTS.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </div>
            </div>
          </div>
        </Section>

        {/* 2 · Ideal Customer Profiles (ICP + Personas, per profile) */}
        <Section
          num={2}
          title="Ideal Customer Profiles"
          sub="The companies and people to reach · one block per profile"
          complete={secComplete[2]}
          open={openSec === 2}
          onToggle={() => toggle(2)}
          onContinue={() => saveAndContinue(2)}
          hideFoot
        >
          <div className="panel-pad">
            <div className="brief-subdiv first">ICP List</div>
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
              <button className="icp-pill add" onClick={newIcp}>
                ＋ New ICP
              </button>
            </div>

            <div className="grid2">
              <div className="field">
                <label>ICP name</label>
                <input
                  className="input"
                  value={icps[icpSel].short}
                  placeholder="e.g. ICP A"
                  onChange={(e) => updateIcp({ short: e.target.value })}
                />
              </div>
              <div className="field">
                <label>Segment label</label>
                <input
                  className="input"
                  value={icps[icpSel].tag}
                  placeholder="e.g. Primary persona"
                  onChange={(e) => updateIcp({ tag: e.target.value })}
                />
              </div>
            </div>
            <div className="field">
              <label>
                Persona <span className="opt">· optional</span>
              </label>
              <textarea
                className="textarea"
                value={icps[icpSel].persona}
                placeholder="Describe this buyer profile, their role, and why they buy."
                onChange={(e) => updateIcp({ persona: e.target.value })}
              />
            </div>

            <div className="brief-subdiv">Ideal Customer Profile</div>
            <div className="field">
              <Lbl
                req
                help={
                  'List the specific sectors. "Everyone" usually means the targeting needs sharpening.'
                }
              >
                Target industries / verticals
              </Lbl>
              <TagInput
                value={f.industries}
                onChange={(v) => setIcpField("industries", v)}
                placeholder="Type a sector, press Enter"
                invalid={submitted && !f.industries.length}
              />
            </div>
            <div className="grid2">
              <div className="field">
                <Lbl req help="By employee count and/or revenue.">
                  Target company size
                </Lbl>
                <input
                  className={errCls(filled(f.companySize))}
                  value={f.companySize}
                  placeholder="e.g. 50–500 employees"
                  onChange={(e) => setIcpField("companySize", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl help="Helps refine list and tone.">Company maturity / stage</Lbl>
                <select
                  className="select"
                  value={f.maturity}
                  onChange={(e) => setIcpField("maturity", e.target.value)}
                >
                  <option value="">Select…</option>
                  {MATURITY_OPTS.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="field">
              <Lbl req help="Countries, regions, or cities to focus on.">
                Target geographies
              </Lbl>
              <TagInput
                value={f.geographies}
                onChange={(v) => setIcpField("geographies", v)}
                placeholder="e.g. United States, UK, Singapore"
                invalid={submitted && !f.geographies.length}
              />
            </div>
            <div className="field">
              <Lbl help="If you can answer this, it unlocks tech-stack-based targeting.">
                Technologies your ideal customer uses
              </Lbl>
              <TagInput
                value={f.technologies}
                onChange={(v) => setIcpField("technologies", v)}
                placeholder="e.g. Salesforce, Shopify, Workday"
              />
            </div>

            <div className="brief-subdiv">Target personas</div>
            <div className="field">
              <Lbl req help={'The exact titles, not "decision makers". Be specific.'}>
                Primary job titles to target
              </Lbl>
              <TagInput
                value={f.jobTitles}
                onChange={(v) => setIcpField("jobTitles", v)}
                placeholder="e.g. Head of Sales, VP Sales, CRO"
                invalid={submitted && !f.jobTitles.length}
              />
            </div>
            <div className="field">
              <Lbl req help="Select all that apply.">
                Seniority level
              </Lbl>
              <PillGroup
                options={SENIORITY_OPTS}
                value={f.seniority}
                onChange={(v) => setIcpField("seniority", v)}
                invalid={submitted && !f.seniority.length}
              />
            </div>
            <div className="grid2">
              <div className="field">
                <Lbl req help="Which teams these people sit in.">
                  Departments / functions
                </Lbl>
                <TagInput
                  value={f.departments}
                  onChange={(v) => setIcpField("departments", v)}
                  placeholder="e.g. Sales, Marketing, Finance"
                  invalid={submitted && !f.departments.length}
                />
              </div>
              <div className="field">
                <Lbl help="Often different people. Shapes who we target first.">
                  Economic buyer vs. champion
                </Lbl>
                <input
                  className="input"
                  value={f.buyerVsChampion}
                  placeholder="e.g. CFO signs off, Head of Ops champions"
                  onChange={(e) => setIcpField("buyerVsChampion", e.target.value)}
                />
              </div>
            </div>
            <div className="field">
              <Lbl help="Personas that look right but never convert.">
                Titles to explicitly avoid
              </Lbl>
              <TagInput
                value={f.avoidTitles}
                onChange={(v) => setIcpField("avoidTitles", v)}
                placeholder="e.g. Procurement, junior analysts"
              />
            </div>

            <div className="icp-foot">
              <div className="est">
                <b>
                  <Sample>n</Sample>
                </b>{" "}
                estimated matching accounts <Sample>sample</Sample> · refreshed placeholder date
              </div>
              <div className="row">
                <button className="btn btn-danger btn-sm" onClick={delIcp}>
                  Delete
                </button>
                <button className="btn btn-accent btn-sm" onClick={() => saveAndContinue(2)}>
                  Save &amp; continue
                </button>
              </div>
            </div>
          </div>
        </Section>

        {/* 3 · Message Inputs */}
        <Section
          num={3}
          title="Message Inputs"
          sub="The raw material for your email copy"
          complete={secComplete[3]}
          open={openSec === 3}
          onToggle={() => toggle(3)}
          onContinue={() => saveAndContinue(3)}
        >
          <div className="panel-pad">
            <div className="field">
              <Lbl
                req
                help="Specific, concrete benefits. Push yourself to name three distinct ones."
              >
                Top 3 value propositions
              </Lbl>
              {[0, 1, 2].map((i) => (
                <input
                  key={i}
                  className={clsx(
                    "input",
                    submitted && i === 0 && !brief.valueProps.some((v) => v.trim()) && "err"
                  )}
                  style={{ marginBottom: i < 2 ? 10 : 0 }}
                  value={brief.valueProps[i] ?? ""}
                  placeholder={"Value prop " + (i + 1)}
                  onChange={(e) => setValueProp(i, e.target.value)}
                />
              ))}
            </div>
            <div className="field">
              <Lbl
                req
                help="Notable clients, metrics, awards, funding. This is what makes cold email believable."
              >
                Proof points / credibility markers
              </Lbl>
              <textarea
                className={errCls(filled(brief.proofPoints), "textarea")}
                value={brief.proofPoints}
                onChange={(e) => setB("proofPoints", e.target.value)}
              />
            </div>
            <div className="field">
              <Lbl
                req
                help="Trigger events that suggest someone is in-market. Drives targeting and hooks."
              >
                What signals a prospect is ready?
              </Lbl>
              <textarea
                className={errCls(filled(brief.signals), "textarea")}
                value={brief.signals}
                onChange={(e) => setB("signals", e.target.value)}
              />
            </div>
            <div className="grid2">
              <div className="field">
                <Lbl help="Pre-arms our reply handling.">Common objections you hear</Lbl>
                <textarea
                  className="textarea"
                  value={brief.objections}
                  onChange={(e) => setB("objections", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl help="Helps with positioning.">Competitors you&apos;re compared to</Lbl>
                <textarea
                  className="textarea"
                  value={brief.competitors}
                  onChange={(e) => setB("competitors", e.target.value)}
                />
              </div>
            </div>
            <div className="grid2">
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl req help="How the emails should feel.">
                  Tone preference
                </Lbl>
                <select
                  className={errCls(filled(brief.tone), "select")}
                  value={brief.tone}
                  onChange={(e) => setB("tone", e.target.value)}
                >
                  <option value="">Select…</option>
                  {TONE_OPTS.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl req help="Select all that apply.">
                  Language(s) for outreach
                </Lbl>
                <PillGroup
                  options={LANGUAGE_OPTS}
                  value={brief.languages}
                  onChange={(v) => setB("languages", v)}
                  invalid={submitted && !brief.languages.length}
                />
                {brief.languages.includes("Other") && (
                  <input
                    className="input"
                    style={{ marginTop: 10 }}
                    value={brief.languageOther}
                    placeholder="If other, please specify"
                    onChange={(e) => setB("languageOther", e.target.value)}
                  />
                )}
              </div>
            </div>
          </div>
        </Section>

        {/* 4 · Exclusions & Guardrails */}
        <Section
          num={4}
          title="Exclusions & Guardrails"
          sub="Who we must never contact"
          complete={secComplete[4]}
          open={openSec === 4}
          onToggle={() => toggle(4)}
          onContinue={() => saveAndContinue(4)}
        >
          <div className="panel-pad">
            <div className="brief-callout">
              <span className="ci">!</span>
              <div>
                <b>Please don&apos;t rush this section.</b> Exclusions are the single most important
                safeguard. Contacting your existing customers or active deals is the fastest way to
                cause a problem, so the more complete this is, the safer your campaign.
              </div>
            </div>
            <div className="field">
              <Lbl req help="We will never contact these. A list of company domains is ideal.">
                Existing customers to exclude
              </Lbl>
              <textarea
                className={errCls(filled(brief.excludeCustomers), "textarea")}
                value={brief.excludeCustomers}
                placeholder="Paste company names or domains, one per line"
                onChange={(e) => setB("excludeCustomers", e.target.value)}
              />
              <div className="brief-upload">
                <label className="btn btn-ghost btn-sm">
                  <span className="up-ico">↥</span> Upload CSV
                  <input type="file" accept=".csv,text/csv" hidden onChange={onCsv("customers")} />
                </label>
                <span className="brief-hint">
                  {csvNames.customers
                    ? "Attached: " + csvNames.customers
                    : "Or upload a CSV of customer domains."}
                </span>
              </div>
            </div>
            <div className="field">
              <Lbl
                req
                help="Prospects already in your sales process. Double-touching these creates friction."
              >
                Active deals / pipeline to exclude
              </Lbl>
              <textarea
                className={errCls(filled(brief.excludeDeals), "textarea")}
                value={brief.excludeDeals}
                placeholder="Paste company names or domains, one per line"
                onChange={(e) => setB("excludeDeals", e.target.value)}
              />
              <div className="brief-upload">
                <label className="btn btn-ghost btn-sm">
                  <span className="up-ico">↥</span> Upload CSV
                  <input type="file" accept=".csv,text/csv" hidden onChange={onCsv("deals")} />
                </label>
                <span className="brief-hint">
                  {csvNames.deals
                    ? "Attached: " + csvNames.deals
                    : "Or upload a CSV of pipeline domains."}
                </span>
              </div>
            </div>
            <div className="field">
              <Lbl help="Competitors, partners, investors, or any sensitive relationships to keep off the list.">
                Competitors & do-not-contact (any reason)
              </Lbl>
              <textarea
                className="textarea"
                value={brief.doNotContact}
                placeholder="Competitors, partners, investors, sensitive relationships — one per line"
                onChange={(e) => setB("doNotContact", e.target.value)}
              />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <Lbl help="Any rules specific to your industry we should know about.">
                Compliance or legal constraints
              </Lbl>
              <input
                className="input"
                value={brief.compliance}
                placeholder="e.g. Cannot contact public sector entities"
                onChange={(e) => setB("compliance", e.target.value)}
              />
            </div>
          </div>
        </Section>

        {/* 5 · Logistics & Handoff */}
        <Section
          num={5}
          title="Logistics & Handoff"
          sub="How meetings and updates flow to you"
          complete={secComplete[5]}
          open={openSec === 5}
          onToggle={() => toggle(5)}
          onContinue={() => saveAndContinue(5)}
        >
          <div className="panel-pad">
            <div className="field">
              <Lbl
                req
                help="A calendar link, a specific rep's calendar, or round-robin across a team."
              >
                Where should booked meetings land?
              </Lbl>
              <input
                className={errCls(filled(brief.meetingsLand))}
                value={brief.meetingsLand}
                placeholder="e.g. Calendly link, or round-robin across 3 AEs"
                onChange={(e) => setB("meetingsLand", e.target.value)}
              />
            </div>
            <div className="field">
              <Lbl req help="Names and titles of the people whose calendars we're booking into.">
                Who attends the meetings?
              </Lbl>
              <input
                className={errCls(filled(brief.attendees))}
                value={brief.attendees}
                placeholder="e.g. Jane Doe (AE), John Smith (Sales Lead)"
                onChange={(e) => setB("attendees", e.target.value)}
              />
            </div>
            <div className="grid2">
              <div className="field">
                <Lbl req help="Days, times, time zone.">
                  Availability constraints
                </Lbl>
                <input
                  className={errCls(filled(brief.availability))}
                  value={brief.availability}
                  placeholder="e.g. Tue–Thu, 10am–4pm GMT"
                  onChange={(e) => setB("availability", e.target.value)}
                />
              </div>
              <div className="field">
                <Lbl req help="How we'll send updates and reply alerts.">
                  Preferred channel with us
                </Lbl>
                <select
                  className={errCls(filled(brief.channel), "select")}
                  value={brief.channel}
                  onChange={(e) => setB("channel", e.target.value)}
                >
                  <option value="">Select…</option>
                  {CHANNEL_OPTS.map((o) => (
                    <option key={o}>{o}</option>
                  ))}
                </select>
              </div>
            </div>
            <div className="grid2">
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl req help="The person we coordinate with day to day.">
                  Main point of contact
                </Lbl>
                <input
                  className={errCls(filled(brief.contact))}
                  value={brief.contact}
                  placeholder="Name, role, email"
                  onChange={(e) => setB("contact", e.target.value)}
                />
              </div>
              <div className="field" style={{ marginBottom: 0 }}>
                <Lbl
                  req
                  help="Sometimes different from the point of contact. Clarifying now avoids delays."
                >
                  Who has approval authority?
                </Lbl>
                <input
                  className={errCls(filled(brief.approver))}
                  value={brief.approver}
                  placeholder="Name, role"
                  onChange={(e) => setB("approver", e.target.value)}
                />
              </div>
            </div>
          </div>
        </Section>

        {/* 6 · Targets & Definitions */}
        <Section
          num={6}
          title="Targets & Definitions"
          sub="What success looks like, and how we measure it"
          complete={secComplete[6]}
          open={openSec === 6}
          onToggle={() => toggle(6)}
          onContinue={() => saveAndContinue(6)}
          last
        >
          <div className="panel-pad">
            <div className="field">
              <Lbl req help="Sets expectations against your plan. Surfaces any mismatch early.">
                Qualified meetings expected per month
              </Lbl>
              <input
                type="number"
                min={0}
                className={errCls(filled(brief.meetingsPerMonth))}
                value={brief.meetingsPerMonth}
                placeholder="e.g. 15"
                onChange={(e) => setB("meetingsPerMonth", e.target.value)}
              />
            </div>
            <div className="field">
              <Lbl
                req
                help="The most important definition in this form. We reconcile it with our standard before launch so billing is never ambiguous."
              >
                What counts as a &quot;qualified meeting&quot; for you?
              </Lbl>
              <textarea
                className={errCls(filled(brief.qualifiedDef), "textarea")}
                value={brief.qualifiedDef}
                onChange={(e) => setB("qualifiedDef", e.target.value)}
              />
            </div>
            <div className="field" style={{ marginBottom: 0 }}>
              <Lbl help="Aligns expectations and frames our first review together.">
                What does a successful first 90 days look like?
              </Lbl>
              <textarea
                className="textarea"
                value={brief.first90}
                onChange={(e) => setB("first90", e.target.value)}
              />
            </div>
          </div>
        </Section>
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
              <button className="btn btn-accent btn-sm" onClick={research}>
                Research prospects from ICP
              </button>
            </div>
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
            <button className="btn btn-primary btn-sm" onClick={createBatch}>
              Create batch
            </button>
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
            <select className="select" value={fIcp} onChange={(e) => setFIcp(e.target.value)}>
              <option value="">All ICPs</option>
              {icps.map((p) => (
                <option key={p.short}>{p.short}</option>
              ))}
            </select>
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
        </div>
      </section>

      {/* SENDOUT BATCH */}
      <section className={clsx("tabpane", tab === "batches" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 12 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            Batches sent for client approval · status updates as the client responds
          </div>
          <div className="row" style={{ gap: 10, alignItems: "center" }}>
            <Link href={`/${client}/client-status#approval`} className="btn btn-ghost btn-2xs">
              Edit approval email
            </Link>
            <span className="badge badge-warn">
              <span className="bdot" />
              {pendingBatches} pending approval
            </span>
          </div>
        </div>
        <div className="sob">
          {batches.map((b, i) => {
            const open = openBatch === b.name;
            return (
              <div className={clsx("sob-item", open && "open")} key={b.name} id={"sob-item-" + i}>
                <div
                  className="sob-card"
                  role="button"
                  tabIndex={0}
                  aria-expanded={open}
                  onClick={() => toggleBatch(b.name, "sob-item-" + i, open)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleBatch(b.name, "sob-item-" + i, open);
                    }
                  }}
                >
                  <div className="sob-ico">B{i + 1}</div>
                  <div className="sob-main">
                    <div className="sob-name">
                      {b.name} <Sample>sample</Sample>
                    </div>
                    <div className="sob-meta">
                      <b style={{ color: "var(--ink)" }}>{b.approved}</b> approved ·{" "}
                      <b style={{ color: "var(--ink)" }}>{b.count}</b> total prospects · sourced
                      from {b.icp}
                    </div>
                    <div className="sob-dates">
                      {(
                        [
                          ["Created", b.createdAt],
                          ["Approved", b.approvedAt],
                          ["Sent", b.sentAt],
                        ] as [string, string | undefined][]
                      )
                        .filter((e): e is [string, string] => Boolean(e[1]))
                        .map(([label, d]) => (
                          <span className="sob-date" key={label}>
                            {label} {fmtShortDate(d)} · <b>{daysAgoLabel(d)}</b>
                          </span>
                        ))}
                      {!b.approvedAt && <span className="sob-date warn">Not yet approved</span>}
                    </div>
                  </div>
                  {b.status === "Pending" && (
                    <button
                      className="btn btn-accent btn-sm"
                      onClick={(e) => {
                        e.stopPropagation();
                        sendApproval(b.name);
                      }}
                    >
                      {b.sentAt ? "Follow-Up Approval" : "Send approval email"}
                    </button>
                  )}
                  <span className={clsx("badge", BATCH_STATUS_CLS[b.status] || "badge-neutral")}>
                    <span className="bdot" />
                    {b.status}
                  </span>
                  <span className="sob-chev" aria-hidden>
                    ⌄
                  </span>
                </div>
                {open && (
                  <div className="sob-detail">
                    <div className="sob-scroll">
                      <table className="tbl">
                        <thead>
                          <tr>
                            <th>Prospect</th>
                            <th>Company</th>
                            <th>Approval</th>
                          </tr>
                        </thead>
                        <tbody>
                          {batchProspects(b).map((p, j) => (
                            <tr key={j}>
                              <td>
                                <span className="nm">{p.name}</span> <Sample>sample</Sample>
                              </td>
                              <td className="muted">{p.company}</td>
                              <td>
                                <span
                                  className={clsx(
                                    "badge",
                                    BATCH_STATUS_CLS[p.status] || "badge-neutral"
                                  )}
                                >
                                  <span className="bdot" />
                                  {p.status}
                                </span>
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                    <div className="sob-more">
                      {b.count} prospects · {b.approved} approved · {b.count - b.approved} pending
                    </div>
                  </div>
                )}
              </div>
            );
          })}
        </div>
      </section>

      {/* CAMPAIGN */}
      <section className={clsx("tabpane", tab === "campaign" && "active")}>
        <div className="between" style={{ marginBottom: 18, flexWrap: "wrap", gap: 14 }}>
          <div className="section-label" style={{ marginBottom: 0 }}>
            Campaigns · variants and send status per sendout batch
          </div>
          <button
            className="btn btn-ghost btn-sm"
            onClick={() => {
              setCampaigns((s) => [
                ...s,
                {
                  name: "Campaign " + (s.length + 1),
                  batch: batches[0]?.name || "None",
                  status: "Pending" as const,
                  variants: ["A", "B", "C"],
                },
              ]);
              toast("Campaign " + (campaigns.length + 1) + " created");
            }}
          >
            ＋ New campaign
          </button>
        </div>
        <div>
          {campaigns.map((cp, ci) => {
            const open = openCamp === ci;
            const live = cp.status === "Live";
            const cb = batches.find((x) => x.name === cp.batch);
            // A campaign can only send once its batch is client-approved.
            const batchNotApproved = cb?.status !== "Approved";
            const blockReason =
              cb?.status === "Rejected"
                ? "Batch was rejected"
                : !cb
                  ? "No batch linked"
                  : "Batch pending approval";
            const size = cb?.count ?? 0;
            const sendN = live ? size : 0;
            const openN = live ? Math.round(size * 0.42) : 0;
            const replyN = live ? Math.round(size * 0.13) : 0;
            const bookedN = live ? Math.round(size * 0.05) : 0;
            return (
              <div className={clsx("camp", open && "open")} key={ci} id={"camp-" + ci}>
                <div
                  className="camp-head"
                  role="button"
                  tabIndex={0}
                  aria-expanded={open}
                  onClick={() => toggleCamp(ci, open)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter" || e.key === " ") {
                      e.preventDefault();
                      toggleCamp(ci, open);
                    }
                  }}
                >
                  <div className="ct">
                    <span className="vtag">{ci + 1}</span>
                    {cp.name} <Sample>sample</Sample>
                  </div>
                  <div className="cmeta">
                    <span className="muted">Sendout batch</span>
                    <select
                      className="select select-sm"
                      style={{ minWidth: 118 }}
                      value={cp.batch}
                      onClick={(e) => e.stopPropagation()}
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
                      <span className="bdot" />
                      {cp.variants.length} variants
                    </span>
                    {!live && (
                      <button
                        className="btn btn-accent btn-sm"
                        disabled={batchNotApproved}
                        title={batchNotApproved ? blockReason + " — can't send yet" : undefined}
                        onClick={(e) => {
                          e.stopPropagation();
                          if (batchNotApproved) return;
                          setCampaigns((s) =>
                            s.map((c, i) => (i === ci ? { ...c, status: "Live" } : c))
                          );
                          toast(cp.name + " launched · sending to " + cp.batch);
                        }}
                      >
                        Send campaign
                      </button>
                    )}
                    {!live && batchNotApproved && (
                      <span className="muted" style={{ fontSize: 12 }}>
                        {blockReason}
                      </span>
                    )}
                    {!live && (
                      <button
                        className="btn btn-ghost btn-sm camp-del"
                        onClick={(e) => {
                          e.stopPropagation();
                          deleteCampaign(ci);
                        }}
                        aria-label={"Delete " + cp.name}
                      >
                        Delete
                      </button>
                    )}
                    <span className="camp-chev" aria-hidden>
                      ⌄
                    </span>
                  </div>
                </div>
                <div className="camp-body">
                  <div className="camp-stats">
                    <div className="cstat">
                      <div className="cl">Deploy status</div>
                      <div className="cv">
                        <span className={clsx("badge", live ? "badge-ok" : "badge-warn")}>
                          <span className="bdot" />
                          {live ? "Live" : "Pending launch"}
                        </span>
                      </div>
                    </div>
                    <div className="cstat">
                      <div className="cl">Total batch size</div>
                      <div className="cv">{size}</div>
                    </div>
                    <div className="cstat">
                      <div className="cl">Sending count</div>
                      <div className="cv">{sendN}</div>
                    </div>
                    <div className="cstat">
                      <div className="cl">Open count</div>
                      <div className="cv">{openN}</div>
                    </div>
                    <div className="cstat">
                      <div className="cl">Reply count</div>
                      <div className="cv">{replyN}</div>
                    </div>
                    <div className="cstat">
                      <div className="cl">Booked meeting</div>
                      <div className="cv">{bookedN}</div>
                    </div>
                  </div>
                  {open && (
                    <Variants
                      tags={cp.variants}
                      editable={!live}
                      campName={cp.name}
                      bodies={variantBodies}
                      editKey={editVar}
                      onRemove={(tag) => removeVariant(ci, tag)}
                      onAdd={() => addVariant(ci)}
                      onEdit={(tag) => editVariant(cp.name, tag)}
                      onBody={(tag, val) => setVariantBody(cp.name, tag, val)}
                    />
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </section>

      {/* REPLY QUEUE */}
      <section className={clsx("tabpane", tab === "replies" && "active")}>
        <div
          className="row"
          style={{ marginBottom: 18, justifyContent: "flex-end", flexWrap: "wrap", gap: 12 }}
        >
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
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          {replies.map((r, i) => {
            // One source of truth for the two reply modes (inbound reply vs follow-up nudge).
            const c = r.nudge ? NUDGE_COPY : { ...REPLY_COPY, body: r.quote };
            return (
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
                      {r.nudge && <span className="ttag nudge">Follow-up nudge</span>}
                    </div>
                  </div>
                  <span className={clsx("badge", r.badge)}>
                    <span className="bdot" />
                    {r.cls}
                  </span>
                </div>
                <div className="reply-quote">
                  <div className="reply-qhead">
                    <span className="ql">{c.qhead}</span>
                    <span className="reply-date">
                      {c.datePrefix}
                      {fmtShortDate(r.repliedAt)} · {daysAgoLabel(r.repliedAt)}
                    </span>
                  </div>
                  {c.body}
                </div>
                <div className="reply-draft">
                  <div className="dl">
                    {c.draftLabel} <Sample>auto-draft</Sample>
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
                    <button className="btn btn-ghost btn-sm" onClick={() => toggleEdit(i)}>
                      {r.editing ? "Done editing" : "Edit draft"}
                    </button>
                    <button
                      className="btn btn-accent btn-sm"
                      onClick={() => {
                        finishReply(i, c.done);
                        toast(c.done);
                      }}
                    >
                      {c.cta}
                    </button>
                  </div>
                </div>
                <div className="reply-sent-banner">
                  <span>✓</span>
                  <span>{r.done}</span>
                </div>
              </div>
            );
          })}
          {replyCamp && inViewReplies.length === 0 && (
            <div className="sum-empty">No replies for {replyCamp} yet.</div>
          )}
        </div>
        <div
          className={clsx(
            "queue-empty",
            inViewReplies.length > 0 && remainingInView === 0 && "show"
          )}
        >
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
              <h3>Billing Ledger</h3>
              <div className="ph-sub">
                Only completed, qualified meetings are billable · all rows <Sample>sample</Sample>
              </div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={exportLedgerCsv}>
              Export CSV
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
                      <span className={clsx("badge", ou.outcomeBadge)}>
                        <span className="bdot" />
                        {ou.outcome}
                      </span>
                    </td>
                    <td className="muted">{ou.feedback}</td>
                    <td>
                      <span className={clsx("badge", ou.billingBadge)}>
                        <span className="bdot" />
                        {ou.billing}
                      </span>
                    </td>
                    <td style={{ textAlign: "right" }} className="tnum">
                      {ou.billing === "Billed" ? (
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
          <select
            className="select select-sm"
            style={{ minWidth: 160 }}
            value={sumCamp}
            onChange={(e) => setSumCamp(e.target.value)}
          >
            <option value="">All campaigns</option>
            {campaigns.map((c) => (
              <option key={c.name}>{c.name}</option>
            ))}
          </select>
        </div>
        <div>
          {recapsInView.map((rc, sx) => {
            const recUrl = `https://meet.google.com/rec/${rc.recId}`;
            return (
              <div className="sum-card" key={rc.recId}>
                <div className="sum-tags">
                  <span className="stag">{rc.campaign}</span>
                  <span className="stag">{rc.batch}</span>
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
                  <span className="sk">Recording</span>
                  <span className="sv">
                    <a className="rec-link" href={recUrl} target="_blank" rel="noopener noreferrer">
                      {recUrl}
                    </a>
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
                <div className="srow">
                  <span className="sk">Final conversion</span>
                  <span className="sv">
                    <span className={clsx("badge", rc.won ? "badge-ok" : "badge-neutral")}>
                      <span className="bdot" />
                      {rc.won ? "Deal won" : "No deal"}
                    </span>
                  </span>
                </div>
              </div>
            );
          })}
          {recapsInView.length === 0 && (
            <div className="sum-empty">No meeting recaps for {sumCamp} yet.</div>
          )}
        </div>
      </section>
    </>
  );
}

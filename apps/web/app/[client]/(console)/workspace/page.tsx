"use client";
import { useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { useToast } from "@/components/Toast";
import { highlightBody } from "@/lib/tmpl";
import { type RowError, mergeExclusionText, parseExclusionCsv } from "@/lib/csv";
import {
  type IcpApi,
  type IcpSuggestion,
  type ResearchSpecResult,
  createIcp as apiCreateIcp,
  deleteIcp as apiDeleteIcp,
  getBrief,
  getResearchSpec,
  listIcps,
  putBrief,
  structureBrief,
  updateIcp as apiUpdateIcp,
} from "@/lib/api";
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
type Icp = { id?: string; short: string; tag: string; persona: string; fields: IcpFields };
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
  noExcludeCustomers: boolean;
  noExcludeDeals: boolean;
  doNotContact: string;
  noDoNotContact: boolean;
  compliance: string;
  attendeeEmails: string;
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

// An all-empty brief (every key present so the controlled inputs stay controlled). The live
// brief loaded from the API is merged over this, so missing keys default to empty, not sample.
const blankBrief = (): Brief => ({
  companyName: "",
  website: "",
  sell: "",
  problem: "",
  dealSize: "",
  salesCycle: "",
  valueProps: ["", "", ""],
  proofPoints: "",
  signals: "",
  objections: "",
  competitors: "",
  tone: "",
  languages: [],
  languageOther: "",
  excludeCustomers: "",
  excludeDeals: "",
  noExcludeCustomers: false,
  noExcludeDeals: false,
  doNotContact: "",
  noDoNotContact: false,
  compliance: "",
  attendeeEmails: "",
  attendees: "",
  availability: "",
  channel: "",
  contact: "",
  approver: "",
  meetingsPerMonth: "",
  qualifiedDef: "",
  first90: "",
});

const blankIcp = (): Icp => ({
  short: "ICP A",
  tag: "",
  persona: "",
  fields: blankFields(),
});

// The ICP card model ⇄ the API's {name, tag, data} document (persona + fields live in data).
const icpToApi = (icp: Icp) => ({
  name: icp.short,
  tag: icp.tag,
  data: { persona: icp.persona, fields: icp.fields },
});
const apiToIcp = (a: IcpApi): Icp => {
  const d = (a.data ?? {}) as { persona?: string; fields?: Partial<IcpFields> };
  return {
    id: a.id,
    short: a.name,
    tag: a.tag,
    persona: d.persona ?? "",
    fields: { ...blankFields(), ...(d.fields ?? {}) },
  };
};

// Read-only chips for a ResearchSpec value list (— when empty). Reuses the ICP card grammar.
function SpecChips({ items, warn }: { items?: string[]; warn?: boolean }) {
  if (!items || !items.length) return <span className="ph">—</span>;
  return (
    <div className="icp-chips">
      {items.map((v, i) => (
        <span key={i} className={"icp-chip" + (warn ? " warn" : "")}>
          {v}
        </span>
      ))}
    </div>
  );
}

// The LLM-generated ResearchSpec, rendered for operator review with existing classes only.
// Always rendered: the Structure/Re-structure control lives in this panel's header, so the
// first spec is generated from here too. Before any spec exists, an empty state is shown.
function SpecReview({
  spec,
  structuring,
  saving,
  completePct,
  onStructure,
  onAcceptIcp,
}: {
  spec: ResearchSpecResult | null;
  structuring: boolean;
  saving: boolean;
  completePct: number;
  onStructure: () => void;
  onAcceptIcp: (s: IcpSuggestion) => void;
}) {
  const s = (spec?.spec ?? {}) as {
    company_search?: {
      industries_include?: string[];
      description_keywords_include?: string[];
      employee_count?: { min?: number | null; max?: number | null };
      locations_include?: { countries?: string[] };
      max_results?: number;
    };
    people_search?: { job_title_keywords?: string[] }[];
    exclusions?: { domains?: string[] };
  };
  const cs = s.company_search ?? {};
  const titles = (s.people_search ?? []).flatMap((p) => p.job_title_keywords ?? []);
  const ec = cs.employee_count;
  const size =
    ec?.min != null && ec?.max != null
      ? `${ec.min}–${ec.max}`
      : ec?.min != null
        ? `${ec.min}+`
        : ec?.max != null
          ? `up to ${ec.max}`
          : null;
  const blocked = structuring || saving || completePct < 100;
  return (
    <div className="panel" style={{ marginTop: 18 }}>
      <div className="panel-head">
        <div>
          <h3>Prospect Scope</h3>
          <div className="ph-sub">
            Complete all 6 sections of the brief first. We summarize the full brief to source
            prospects.
          </div>
        </div>
        <div className="row" style={{ gap: 8 }}>
          {/* The span carries the tooltip; the disabled button gets pointer-events:none so the
              hover falls through to the span and the title shows (disabled buttons swallow it). */}
          <span
            style={{ display: "inline-flex" }}
            title={
              completePct < 100
                ? "Complete all 6 sections of the brief first. We summarize the full brief to source prospects in Clay."
                : "Summarize this brief with AI into a Clay-ready prospect scope."
            }
          >
            <button
              type="button"
              className="btn btn-accent btn-sm"
              disabled={blocked}
              style={blocked ? { pointerEvents: "none" } : undefined}
              onClick={onStructure}
            >
              {structuring ? "Generating…" : spec ? "Regenerate Scope" : "Generate Scope"}
            </button>
          </span>
        </div>
      </div>
      {!spec ? (
        <div className="panel-pad">
          <div className="sum-empty">
            Not generated yet · fill in the brief, then generate your Clay-ready scope.
          </div>
        </div>
      ) : (
        <div className="panel-pad">
          <div className="icp-grid">
            <div className="icp-cell">
              <div className="k">Industries</div>
              <div className="v">
                <SpecChips items={cs.industries_include} />
              </div>
            </div>
            <div className="icp-cell">
              <div className="k">Company size</div>
              <div className="v">{size ?? <span className="ph">—</span>}</div>
            </div>
            <div className="icp-cell">
              <div className="k">Geography</div>
              <div className="v">
                <SpecChips items={cs.locations_include?.countries} />
              </div>
            </div>
            <div className="icp-cell">
              <div className="k">Keywords</div>
              <div className="v">
                <SpecChips items={cs.description_keywords_include} />
              </div>
            </div>
            <div className="icp-cell">
              <div className="k">Target titles</div>
              <div className="v">
                <SpecChips items={titles} />
              </div>
            </div>
            <div className="icp-cell">
              <div className="k">Exclusions</div>
              <div className="v">
                <SpecChips items={s.exclusions?.domains} warn />
              </div>
            </div>
          </div>
          {spec.gaps.length > 0 && (
            <div className="brief-callout" style={{ marginTop: 8 }}>
              <span className="ci">!</span>
              <div>
                <strong>
                  {spec.gaps.length} gap{spec.gaps.length > 1 ? "s" : ""} to sharpen targeting
                </strong>
                <ul style={{ margin: "8px 0 0", paddingLeft: 18 }}>
                  {spec.gaps.map((g, i) => (
                    <li key={i}>
                      <strong>{g.field}</strong> — {g.ask}
                    </li>
                  ))}
                </ul>
              </div>
            </div>
          )}
          {(spec.icp_suggestions ?? []).map((sug, i) => (
            <div className="icp-suggest" key={i}>
              <div className="is-head">
                <div className="is-title">
                  <span className="badge badge-info">Suggested ICP</span>
                  <strong>{sug.name}</strong>
                  <span className={"badge badge-" + (sug.confidence === "high" ? "ok" : "neutral")}>
                    {sug.confidence} confidence
                  </span>
                </div>
                <button
                  type="button"
                  className="btn btn-accent btn-sm"
                  onClick={() => onAcceptIcp(sug)}
                >
                  Add as ICP
                </button>
              </div>
              <div className="is-why">{sug.rationale}</div>
              {sug.evidence_companies.length > 0 && (
                <div className="is-row">
                  <span className="k">Based on</span>
                  <SpecChips items={sug.evidence_companies} />
                </div>
              )}
              {sug.suggested_industries.length > 0 && (
                <div className="is-row">
                  <span className="k">Industries</span>
                  <SpecChips items={sug.suggested_industries} />
                </div>
              )}
              {sug.suggested_titles.length > 0 && (
                <div className="is-row">
                  <span className="k">Titles</span>
                  <SpecChips items={sug.suggested_titles} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

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

// label + required/done/optional badge + helper line. A required field whose value is filled
// shows a green "Done" badge instead of the red "Required" one.
function Lbl({
  children,
  req,
  done,
  help,
}: {
  children: React.ReactNode;
  req?: boolean;
  done?: boolean;
  help?: string;
}) {
  return (
    <>
      <label>
        {children}
        {done ? (
          <span className="brief-done">Done</span>
        ) : (
          <span className={req ? "brief-req" : "brief-opt"}>{req ? "Required" : "Optional"}</span>
        )}
      </label>
      {help && <div className="brief-help">{help}</div>}
    </>
  );
}

// Data-format guide for the exclusion lists. Each record carries three columns in a fixed
// order — identical to the CSV upload — so the textarea is just inline CSV and the on-screen
// format and the file format are taught once. Shown above each exclusion textarea.
function ExclFormat() {
  return (
    <div className="excl-format" aria-hidden="true">
      <div className="ef-cols">
        <span className="ef-col">company domain</span>
        <span className="ef-sep">,</span>
        <span className="ef-col">company name</span>
        <span className="ef-sep">,</span>
        <span className="ef-col">website</span>
        <span className="ef-note">· one company per line</span>
      </div>
      <div className="ef-ex">tryholdslot.com, HoldSlot, https://tryholdslot.com/</div>
    </div>
  );
}

const EXCL_PLACEHOLDER = "tryholdslot.com, HoldSlot, https://tryholdslot.com/";

// CSV import: field key → the brief text field it fills, plus sane upload guards.
const EXCL_TEXT_KEY: Record<
  "customers" | "deals" | "doNotContact",
  "excludeCustomers" | "excludeDeals" | "doNotContact"
> = {
  customers: "excludeCustomers",
  deals: "excludeDeals",
  doNotContact: "doNotContact",
};
const MAX_CSV_BYTES = 1_000_000; // 1 MB
const MAX_CSV_ROWS = 5000;

// Skipped-row report shown under an exclusion field after an import.
function CsvErrors({ errors, onDismiss }: { errors?: RowError[]; onDismiss: () => void }) {
  if (!errors || errors.length === 0) return null;
  const shown = errors.slice(0, 8);
  return (
    <div className="csv-errors">
      <div className="ce-head">
        <span>
          {errors.length} row{errors.length > 1 ? "s" : ""} skipped — fix and re-upload, or add by
          hand
        </span>
        <button type="button" className="ce-x" onClick={onDismiss} aria-label="Dismiss">
          ✕
        </button>
      </div>
      <ul>
        {shown.map((e) => (
          <li key={e.line}>
            <b>Line {e.line}</b>: {e.reasons.join(", ")}
            {e.raw && <span className="ce-raw"> · {e.raw}</span>}
          </li>
        ))}
      </ul>
      {errors.length > shown.length && (
        <div className="ce-more">+{errors.length - shown.length} more…</div>
      )}
    </div>
  );
}

// collapsible brief section with a Complete / Pending status label
function Section({
  num,
  title,
  sub,
  complete,
  count,
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
  count?: { done: number; total: number };
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
        {count && (
          <span
            className={clsx("brief-count", count.done === count.total && "done")}
            title={count.done + " of " + count.total + " required fields complete"}
          >
            <span className="brief-count-bar" aria-hidden>
              <span style={{ width: (count.done / count.total) * 100 + "%" }} />
            </span>
            {count.done}/{count.total}
          </span>
        )}
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

// Do-not-contact list — the three exclusion sources from the Brief. Everyone here is
// suppressed from every batch and campaign; it is pinned to the top of Approval Batches
// for review and never overlaps a sendout batch.
const EXCLUSIONS: { label: string; tag: string; cls: string; entries: string[] }[] = [
  {
    label: "Existing customers to exclude",
    tag: "Customer",
    cls: "badge-info",
    entries: ["Acme Corp", "Globex Inc", "Initech"],
  },
  {
    label: "Active deals / pipeline to exclude",
    tag: "Active deal",
    cls: "badge-warn",
    entries: ["Umbrella Co", "Soylent Ltd"],
  },
  {
    label: "Competitors & do-not-contact (any reason)",
    tag: "Competitor / DNC",
    cls: "badge-danger",
    entries: ["Competitor A", "Competitor B", "Hooli"],
  },
];
const EXCLUSION_COUNT = EXCLUSIONS.reduce((n, g) => n + g.entries.length, 0);

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
  // Starts with one empty profile so `icps[icpSel]` is always defined; the live ICPs from
  // the API replace this on load (or it stays as the first, unsaved profile).
  const [icps, setIcps] = useState<Icp[]>([blankIcp()]);
  const [icpSel, setIcpSel] = useState(0);
  function newIcp() {
    // Functional append so two rapid clicks can't collide on the same letter/length;
    // capture the new index from the same snapshot so the selection can't go stale either.
    let added = 0;
    setIcps((s) => {
      added = s.length;
      return [
        ...s,
        {
          short: "ICP " + String.fromCharCode(65 + s.length),
          tag: "",
          persona: "",
          fields: blankFields(),
        },
      ];
    });
    setIcpSel(added);
    toast("ICP profile created");
  }
  // Accept an LLM ICP suggestion (derived from the customer list) → a new, prefilled ICP the
  // founder reviews and saves. Jumps to the ICP section so it's edited in context.
  function acceptIcpSuggestion(sug: IcpSuggestion) {
    let added = 0;
    setIcps((s) => {
      added = s.length;
      return [
        ...s,
        {
          short: sug.name || "ICP " + String.fromCharCode(65 + s.length),
          tag: "from customers",
          persona: "",
          fields: {
            ...blankFields(),
            industries: sug.suggested_industries ?? [],
            jobTitles: sug.suggested_titles ?? [],
          },
        },
      ];
    });
    setIcpSel(added);
    setOpenSec(2);
    toast("ICP added from suggestion · review & save");
  }
  function delIcp() {
    if (icps.length <= 1) return toast("Keep at least one ICP", "warn");
    const cur = icps[icpSel];
    if (cur.id) setDeletedIcpIds((s) => [...s, cur.id!]);
    const next = icps.filter((_, i) => i !== icpSel);
    setIcps(next);
    setIcpSel((s) => Math.min(s, next.length - 1));
    toast(cur.short + " deleted", "warn");
  }
  const updateIcp = (patch: Partial<Icp>) =>
    setIcps((s) => s.map((x, i) => (i === icpSel ? { ...x, ...patch } : x)));
  const setIcpField = <K extends keyof IcpFields>(key: K, val: IcpFields[K]) =>
    setIcps((s) =>
      s.map((x, i) => (i === icpSel ? { ...x, fields: { ...x.fields, [key]: val } } : x))
    );

  // Business brief (global sections)
  const [brief, setBrief] = useState<Brief>(blankBrief);
  const [submitted, setSubmitted] = useState(false);
  // CSV attachment name per exclusion field (keyed: "customers", "deals")
  const [csvNames, setCsvNames] = useState<Record<string, string>>({});
  // Invalid/skipped rows from the last import, per field — shown back to the user.
  const [csvErrors, setCsvErrors] = useState<Record<string, RowError[]>>({});
  // CSV import: parse → validate against the three-column contract → merge valid rows
  // (dedupe by domain) into the field → persist immediately → report skipped rows.
  const onCsv =
    (key: "customers" | "deals" | "doNotContact") =>
    async (e: React.ChangeEvent<HTMLInputElement>) => {
      const file = e.target.files?.[0];
      e.target.value = ""; // allow re-uploading the same file
      if (!file) return;

      const textKey = EXCL_TEXT_KEY[key];
      if (!/\.csv$/i.test(file.name) && file.type !== "text/csv") {
        toast("Please upload a .csv file", "warn");
        return;
      }
      if (file.size > MAX_CSV_BYTES) {
        toast("CSV is too large (max 1 MB)", "warn");
        return;
      }
      let text: string;
      try {
        text = await file.text();
      } catch {
        toast("Could not read the file", "warn");
        return;
      }

      const { valid, errors, total } = parseExclusionCsv(text);
      if (total > MAX_CSV_ROWS) {
        toast(`CSV has too many rows (max ${MAX_CSV_ROWS.toLocaleString()})`, "warn");
        return;
      }
      if (valid.length === 0 && errors.length === 0) {
        toast("No rows found in the CSV", "warn");
        return;
      }

      setCsvNames((s) => ({ ...s, [key]: file.name }));
      setCsvErrors((s) => ({ ...s, [key]: errors }));

      if (valid.length === 0) {
        toast("No valid rows — see the issues below", "warn");
        return;
      }

      const { text: merged, added, duplicates } = mergeExclusionText(brief[textKey], valid);
      const next = { ...brief, [textKey]: merged };
      setBrief(next);

      const parts = [`Imported ${added}`];
      if (duplicates) parts.push(`${duplicates} duplicate${duplicates > 1 ? "s" : ""} skipped`);
      if (errors.length) parts.push(`${errors.length} invalid skipped`);
      toast(parts.join(" · "));
      void persist(next); // save to DB immediately (state updates are async — pass the snapshot)
    };
  const setB = <K extends keyof Brief>(key: K, val: Brief[K]) =>
    setBrief((s) => ({ ...s, [key]: val }));
  // "Nothing to exclude" attestation: ticking it clears (and locks) the matching
  // list + any attached CSV so we never carry contradictory data into sourcing.
  const setNoExclude =
    (
      flag: "noExcludeCustomers" | "noExcludeDeals" | "noDoNotContact",
      textKey: "excludeCustomers" | "excludeDeals" | "doNotContact",
      csvKey: string
    ) =>
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const on = e.target.checked;
      setBrief((s) => ({ ...s, [flag]: on, ...(on ? { [textKey]: "" } : {}) }));
      if (on) {
        setCsvNames((s) => ({ ...s, [csvKey]: "" }));
        setCsvErrors((s) => ({ ...s, [csvKey]: [] }));
      }
    };
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
  // --- Phase B: live brief + ICP + ResearchSpec ----------------------------
  const [saving, setSaving] = useState(false);
  const [structuring, setStructuring] = useState(false);
  // True while the brief/ICP/spec are hydrating for this client (initial load + client switch).
  const [loading, setLoading] = useState(true);
  const [spec, setSpec] = useState<ResearchSpecResult | null>(null);
  // IDs of saved ICPs the operator has deleted; flushed to the API on the next save.
  const [deletedIcpIds, setDeletedIcpIds] = useState<string[]>([]);
  // Guards against concurrent persist() runs (rapid section saves / save-during-structure).
  const savingRef = useRef(false);
  // Latest snapshot that arrived while a save was in flight — flushed when it finishes, so a
  // CSV import (or any edit) saved mid-save isn't silently dropped. Last-write-wins.
  const pendingBriefRef = useRef<Brief | null>(null);

  // Hydrate the brief + ICPs + latest spec for this client.
  useEffect(() => {
    if (!client) return;
    let alive = true;
    setLoading(true);
    (async () => {
      // Load independently so one failing endpoint doesn't blank the others.
      const b = await getBrief(client).catch(() => null);
      const ics = await listIcps(client).catch(() => null);
      const rs = await getResearchSpec(client).catch(() => null);
      if (!alive) return;
      if (b) {
        const d = (b.data ?? {}) as Partial<Brief>;
        // Coerce the multi-value fields to arrays so the controlled inputs never crash on a
        // malformed document (the form always writes arrays, but be defensive on read).
        setBrief({
          ...blankBrief(),
          ...d,
          valueProps: Array.isArray(d.valueProps) ? d.valueProps : blankBrief().valueProps,
          languages: Array.isArray(d.languages) ? d.languages : [],
          // Read-migration: the handoff target was renamed `meetingsLand` → `attendeeEmails`.
          // Salvage the old value so a previously-complete §5 isn't silently blanked on load.
          attendeeEmails:
            d.attendeeEmails ||
            (typeof (d as Record<string, unknown>).meetingsLand === "string"
              ? ((d as Record<string, unknown>).meetingsLand as string)
              : ""),
          noExcludeCustomers: !!d.noExcludeCustomers,
          noExcludeDeals: !!d.noExcludeDeals,
          noDoNotContact: !!d.noDoNotContact,
        });
      }
      if (ics) {
        setIcps(ics.length ? ics.map(apiToIcp) : [blankIcp()]);
        setIcpSel(0);
        setDeletedIcpIds([]);
      }
      if (rs) {
        setSpec(rs.latest);
      }
      setLoading(false);
    })();
    return () => {
      alive = false;
    };
  }, [client]);

  // Persist the brief + sync every ICP (create new, update existing, delete removed).
  // Sequential so a new ICP's server id is recorded immediately — a mid-sync failure can
  // never cause the same ICP to be re-created (and duplicated) on the next save.
  async function persist(briefSnapshot: Brief = brief) {
    if (savingRef.current) {
      // Don't drop — queue the latest snapshot and flush it when the in-flight save finishes.
      pendingBriefRef.current = briefSnapshot;
      return;
    }
    savingRef.current = true;
    setSaving(true);
    try {
      await putBrief(client, briefSnapshot as unknown as Record<string, unknown>);
      for (const icp of icps) {
        if (icp.id) {
          await apiUpdateIcp(client, icp.id, icpToApi(icp));
        } else {
          const created = await apiCreateIcp(client, icpToApi(icp));
          // Record the new id immediately (reference-matched) so it survives a later failure.
          setIcps((s) => s.map((x) => (x === icp ? { ...x, id: created.id } : x)));
        }
      }
      for (const id of deletedIcpIds) await apiDeleteIcp(client, id);
      setDeletedIcpIds([]);
    } finally {
      savingRef.current = false;
      setSaving(false);
    }
    // Flush a save that arrived mid-flight (e.g. a CSV import). Latest snapshot only.
    const queued = pendingBriefRef.current;
    if (queued) {
      pendingBriefRef.current = null;
      await persist(queued);
    }
  }

  // Save the brief + ICPs, then structure them into a new ResearchSpec version.
  async function runStructure() {
    setStructuring(true);
    try {
      await persist();
      const rs = await structureBrief(client);
      setSpec(rs);
      toast("Research spec v" + rs.version + " generated");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Structuring failed", "warn");
    } finally {
      setStructuring(false);
    }
  }

  async function saveAndContinue(cur: number) {
    // Surface missing required fields once the operator tries to save.
    setSubmitted(true);
    let ok = true;
    try {
      await persist(); // confirm the save before claiming progress
    } catch (e) {
      ok = false;
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    }
    if (ok) toast("Saved");
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
  // Required fields per section, as booleans (filled = true). Drives both the
  // per-section "x/N" counter and the Complete/Pending status. Section 2's
  // counter tracks the ICP currently being edited (f); its Complete badge still
  // requires every ICP to be ready (icpReady).
  const secReq: Record<number, boolean[]> = {
    1: [
      filled(brief.companyName),
      filled(brief.website),
      filled(brief.sell),
      filled(brief.problem),
      filled(brief.dealSize),
      filled(brief.salesCycle),
    ],
    2: [
      filled(f.industries),
      filled(f.companySize),
      filled(f.geographies),
      filled(f.jobTitles),
      filled(f.seniority),
      filled(f.departments),
    ],
    3: [
      brief.valueProps.some((v) => v.trim()),
      filled(brief.proofPoints),
      filled(brief.signals),
      filled(brief.tone),
      brief.languages.length > 0,
    ],
    4: [
      filled(brief.excludeCustomers) || brief.noExcludeCustomers,
      filled(brief.excludeDeals) || brief.noExcludeDeals,
    ],
    5: [
      filled(brief.attendeeEmails),
      filled(brief.attendees),
      filled(brief.availability),
      filled(brief.channel),
      filled(brief.contact),
      filled(brief.approver),
    ],
    6: [filled(brief.meetingsPerMonth), filled(brief.qualifiedDef)],
  };
  const secCount = (n: number) => ({
    done: secReq[n].filter(Boolean).length,
    total: secReq[n].length,
  });
  // per-section completeness (drives the status label + the top bar)
  const secComplete: Record<number, boolean> = {
    1: secReq[1].every(Boolean),
    2: icpReady,
    3: secReq[3].every(Boolean),
    4: secReq[4].every(Boolean),
    5: secReq[5].every(Boolean),
    6: secReq[6].every(Boolean),
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
    { name: "Campaign 2", batch: "Batch 2", status: "Pending", variants: ["A", "B", "C"] },
  ]);
  // Campaigns can only be linked to client-approved batches — pending/rejected
  // batches are never selectable, so a linked campaign is always safe to send.
  const approvedBatches = batches.filter((b) => b.status === "Approved");

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
  const [exclOpen, setExclOpen] = useState(false);
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
        {loading ? (
          <div className="panel">
            <div className="panel-loading">
              <span className="hs-spinner" aria-hidden="true" />
              Loading your brief…
            </div>
          </div>
        ) : (
          <>
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
              count={secCount(1)}
              open={openSec === 1}
              onToggle={() => toggle(1)}
              onContinue={() => saveAndContinue(1)}
            >
              <div className="panel-pad">
                <div className="grid2">
                  <div className="field">
                    <Lbl
                      req
                      done={filled(brief.companyName)}
                      help="The brand name as it should appear in email signatures."
                    >
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
                    <Lbl
                      req
                      done={filled(brief.website)}
                      help="Used for enrichment context and to verify what you sell."
                    >
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
                    done={filled(brief.sell)}
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
                    done={filled(brief.problem)}
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
                    <Lbl
                      req
                      done={filled(brief.dealSize)}
                      help="Annual contract value. Determines whether the unit economics work."
                    >
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
                    <Lbl
                      req
                      done={filled(brief.salesCycle)}
                      help="Shapes follow-up cadence and time-to-revenue."
                    >
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
              count={secCount(2)}
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
                      key={p.id ?? "new-" + i}
                      className={clsx("icp-pill", i === icpSel && "on")}
                      onClick={() => setIcpSel(i)}
                    >
                      <div className="ipn">{p.short}</div>
                      {p.tag && <div className="ipt">{p.tag}</div>}
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
                    done={filled(f.industries)}
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
                    <Lbl req done={filled(f.companySize)} help="By employee count and/or revenue.">
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
                    <Lbl done={filled(f.maturity)} help="Helps refine list and tone.">
                      Company maturity / stage
                    </Lbl>
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
                  <Lbl
                    req
                    done={filled(f.geographies)}
                    help="Countries, regions, or cities to focus on."
                  >
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
                  <Lbl
                    done={filled(f.technologies)}
                    help="If you can answer this, it unlocks tech-stack-based targeting."
                  >
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
                  <Lbl
                    req
                    done={filled(f.jobTitles)}
                    help={'The exact titles, not "decision makers". Be specific.'}
                  >
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
                  <Lbl req done={filled(f.seniority)} help="Select all that apply.">
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
                    <Lbl req done={filled(f.departments)} help="Which teams these people sit in.">
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
                    <Lbl
                      done={filled(f.buyerVsChampion)}
                      help="Often different people. Shapes who we target first."
                    >
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
                  <Lbl
                    done={filled(f.avoidTitles)}
                    help="Personas that look right but never convert."
                  >
                    Titles to explicitly avoid
                  </Lbl>
                  <TagInput
                    value={f.avoidTitles}
                    onChange={(v) => setIcpField("avoidTitles", v)}
                    placeholder="e.g. Procurement, junior analysts"
                  />
                </div>

                <div className="icp-foot">
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
              count={secCount(3)}
              open={openSec === 3}
              onToggle={() => toggle(3)}
              onContinue={() => saveAndContinue(3)}
            >
              <div className="panel-pad">
                <div className="field">
                  <Lbl
                    req
                    done={brief.valueProps.some((v) => v.trim())}
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
                    done={filled(brief.proofPoints)}
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
                    done={filled(brief.signals)}
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
                    <Lbl done={filled(brief.objections)} help="Pre-arms our reply handling.">
                      Common objections you hear
                    </Lbl>
                    <textarea
                      className="textarea"
                      value={brief.objections}
                      onChange={(e) => setB("objections", e.target.value)}
                    />
                  </div>
                  <div className="field">
                    <Lbl done={filled(brief.competitors)} help="Helps with positioning.">
                      Competitors you&apos;re compared to
                    </Lbl>
                    <textarea
                      className="textarea"
                      value={brief.competitors}
                      onChange={(e) => setB("competitors", e.target.value)}
                    />
                  </div>
                </div>
                <div className="grid2">
                  <div className="field" style={{ marginBottom: 0 }}>
                    <Lbl req done={filled(brief.tone)} help="How the emails should feel.">
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
                    <Lbl req done={filled(brief.languages)} help="Select all that apply.">
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
              count={secCount(4)}
              open={openSec === 4}
              onToggle={() => toggle(4)}
              onContinue={() => saveAndContinue(4)}
            >
              <div className="panel-pad">
                <div className="brief-callout">
                  <span className="ci">!</span>
                  <div>
                    <b>Please don&apos;t rush this section.</b> Exclusions are the single most
                    important safeguard. Contacting your existing customers or active deals is the
                    fastest way to cause a problem, so the more complete this is, the safer your
                    campaign.
                  </div>
                </div>
                <div className={clsx("field", brief.noExcludeCustomers && "is-locked")}>
                  <Lbl
                    req
                    done={filled(brief.excludeCustomers) || brief.noExcludeCustomers}
                    help="We will never contact these. Add one company per line using the three columns below, or upload a CSV. If you have none, tick the box."
                  >
                    Existing customers to exclude
                  </Lbl>
                  <ExclFormat />
                  <textarea
                    className={errCls(
                      filled(brief.excludeCustomers) || brief.noExcludeCustomers,
                      "textarea"
                    )}
                    value={brief.excludeCustomers}
                    placeholder={EXCL_PLACEHOLDER}
                    disabled={brief.noExcludeCustomers}
                    onChange={(e) => setB("excludeCustomers", e.target.value)}
                  />
                  <div className="brief-upload">
                    <label
                      className={clsx(
                        "btn btn-ghost btn-sm",
                        brief.noExcludeCustomers && "disabled"
                      )}
                    >
                      <span className="up-ico">↥</span> Upload CSV
                      <input
                        type="file"
                        accept=".csv,text/csv"
                        hidden
                        disabled={brief.noExcludeCustomers}
                        onChange={onCsv("customers")}
                      />
                    </label>
                    <span className="brief-hint">
                      {csvNames.customers
                        ? "Attached: " + csvNames.customers
                        : "Or upload a CSV with columns: company domain, company name, website."}
                    </span>
                    <label className="brief-none">
                      <input
                        type="checkbox"
                        checked={brief.noExcludeCustomers}
                        onChange={setNoExclude("noExcludeCustomers", "excludeCustomers", "customers")}
                      />
                      We have no existing customers to exclude.
                    </label>
                  </div>
                  <CsvErrors
                    errors={csvErrors.customers}
                    onDismiss={() => setCsvErrors((s) => ({ ...s, customers: [] }))}
                  />
                </div>
                <div className={clsx("field", brief.noExcludeDeals && "is-locked")}>
                  <Lbl
                    req
                    done={filled(brief.excludeDeals) || brief.noExcludeDeals}
                    help="Prospects already in your sales process. Double-touching these creates friction. Same three columns as above, or upload a CSV. If you have none, tick the box."
                  >
                    Active deals / pipeline to exclude
                  </Lbl>
                  <ExclFormat />
                  <textarea
                    className={errCls(
                      filled(brief.excludeDeals) || brief.noExcludeDeals,
                      "textarea"
                    )}
                    value={brief.excludeDeals}
                    placeholder={EXCL_PLACEHOLDER}
                    disabled={brief.noExcludeDeals}
                    onChange={(e) => setB("excludeDeals", e.target.value)}
                  />
                  <div className="brief-upload">
                    <label
                      className={clsx("btn btn-ghost btn-sm", brief.noExcludeDeals && "disabled")}
                    >
                      <span className="up-ico">↥</span> Upload CSV
                      <input
                        type="file"
                        accept=".csv,text/csv"
                        hidden
                        disabled={brief.noExcludeDeals}
                        onChange={onCsv("deals")}
                      />
                    </label>
                    <span className="brief-hint">
                      {csvNames.deals
                        ? "Attached: " + csvNames.deals
                        : "Or upload a CSV with columns: company domain, company name, website."}
                    </span>
                    <label className="brief-none">
                      <input
                        type="checkbox"
                        checked={brief.noExcludeDeals}
                        onChange={setNoExclude("noExcludeDeals", "excludeDeals", "deals")}
                      />
                      We have no active deals in pipeline to exclude.
                    </label>
                  </div>
                  <CsvErrors
                    errors={csvErrors.deals}
                    onDismiss={() => setCsvErrors((s) => ({ ...s, deals: [] }))}
                  />
                </div>
                <div className={clsx("field", brief.noDoNotContact && "is-locked")}>
                  <Lbl
                    done={filled(brief.doNotContact) || brief.noDoNotContact}
                    help="Competitors, partners, investors, or any sensitive relationships to keep off the list. Same three columns as above, or upload a CSV. If you have none, tick the box."
                  >
                    Competitors & do-not-contact (any reason)
                  </Lbl>
                  <ExclFormat />
                  <textarea
                    className="textarea"
                    value={brief.doNotContact}
                    placeholder={EXCL_PLACEHOLDER}
                    disabled={brief.noDoNotContact}
                    onChange={(e) => setB("doNotContact", e.target.value)}
                  />
                  <div className="brief-upload">
                    <label
                      className={clsx("btn btn-ghost btn-sm", brief.noDoNotContact && "disabled")}
                    >
                      <span className="up-ico">↥</span> Upload CSV
                      <input
                        type="file"
                        accept=".csv,text/csv"
                        hidden
                        disabled={brief.noDoNotContact}
                        onChange={onCsv("doNotContact")}
                      />
                    </label>
                    <span className="brief-hint">
                      {csvNames.doNotContact
                        ? "Attached: " + csvNames.doNotContact
                        : "Or upload a CSV with columns: company domain, company name, website."}
                    </span>
                    <label className="brief-none">
                      <input
                        type="checkbox"
                        checked={brief.noDoNotContact}
                        onChange={setNoExclude("noDoNotContact", "doNotContact", "doNotContact")}
                      />
                      We have no competitors or do-not-contact companies.
                    </label>
                  </div>
                  <CsvErrors
                    errors={csvErrors.doNotContact}
                    onDismiss={() => setCsvErrors((s) => ({ ...s, doNotContact: [] }))}
                  />
                </div>
                <div className="field" style={{ marginBottom: 0 }}>
                  <Lbl
                    done={filled(brief.compliance)}
                    help="Any rules specific to your industry we should know about."
                  >
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
              count={secCount(5)}
              open={openSec === 5}
              onToggle={() => toggle(5)}
              onContinue={() => saveAndContinue(5)}
            >
              <div className="panel-pad">
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.attendeeEmails)}
                    help="The email addresses on your side to invite. We create the Google Meet and send the calendar invite to these people — one per line, or comma-separated."
                  >
                    Meeting attendee emails
                  </Lbl>
                  <textarea
                    className={errCls(filled(brief.attendeeEmails), "textarea")}
                    value={brief.attendeeEmails}
                    placeholder={"jane@yourcompany.com\njohn@yourcompany.com"}
                    onChange={(e) => setB("attendeeEmails", e.target.value)}
                  />
                </div>
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.attendees)}
                    help="Names and titles of the people whose calendars we're booking into."
                  >
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
                    <Lbl req done={filled(brief.availability)} help="Days, times, time zone.">
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
                    <Lbl
                      req
                      done={filled(brief.channel)}
                      help="How we'll send updates and reply alerts."
                    >
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
                    <Lbl
                      req
                      done={filled(brief.contact)}
                      help="The person we coordinate with day to day."
                    >
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
                      done={filled(brief.approver)}
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
              count={secCount(6)}
              open={openSec === 6}
              onToggle={() => toggle(6)}
              onContinue={() => saveAndContinue(6)}
              last
            >
              <div className="panel-pad">
                <div className="field">
                  <Lbl
                    req
                    done={filled(brief.meetingsPerMonth)}
                    help="Sets expectations against your plan. Surfaces any mismatch early."
                  >
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
                    done={filled(brief.qualifiedDef)}
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
                  <Lbl
                    done={filled(brief.first90)}
                    help="Aligns expectations and frames our first review together."
                  >
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

            <SpecReview
              spec={spec}
              structuring={structuring}
              saving={saving}
              completePct={completePct}
              onStructure={runStructure}
              onAcceptIcp={acceptIcpSuggestion}
            />
          </>
        )}
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
              {icps.map((p, i) => (
                <option key={p.id ?? "new-" + i}>{p.short}</option>
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
          {/* Pinned do-not-contact batch — always on top, never contacted, excluded everywhere */}
          <div className={clsx("sob-item sob-exclude", exclOpen && "open")}>
            <div
              className="sob-card"
              role="button"
              tabIndex={0}
              aria-expanded={exclOpen}
              onClick={() => setExclOpen((o) => !o)}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  setExclOpen((o) => !o);
                }
              }}
            >
              <div className="sob-ico">⊘</div>
              <div className="sob-main">
                <div className="sob-name">Do-not-contact list</div>
                <div className="sob-meta">
                  <b style={{ color: "var(--danger)" }}>{EXCLUSION_COUNT}</b> suppressed contacts ·
                  never contacted · excluded from every batch &amp; campaign
                </div>
              </div>
              <span className="badge badge-danger">
                <span className="bdot" />
                Excluded
              </span>
              <span className="sob-chev" aria-hidden>
                ⌄
              </span>
            </div>
            {exclOpen && (
              <div className="sob-detail">
                <div className="sob-scroll">
                  <table className="tbl">
                    <thead>
                      <tr>
                        <th>Excluded</th>
                        <th>Type</th>
                        <th>Reason</th>
                      </tr>
                    </thead>
                    <tbody>
                      {EXCLUSIONS.flatMap((g) =>
                        g.entries.map((name) => (
                          <tr key={g.label + name}>
                            <td>
                              <span className="nm">{name}</span> <Sample>sample</Sample>
                            </td>
                            <td>
                              <span className={clsx("badge", g.cls)}>
                                <span className="bdot" />
                                {g.tag}
                              </span>
                            </td>
                            <td className="muted">{g.label}</td>
                          </tr>
                        ))
                      )}
                    </tbody>
                  </table>
                </div>
                <div className="sob-more">
                  Sourced from your Brief exclusions · no prospect in any sendout batch overlaps
                  this list.
                </div>
              </div>
            )}
          </div>
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
            disabled={approvedBatches.length === 0}
            title={approvedBatches.length === 0 ? "Approve a sendout batch first" : undefined}
            onClick={() => {
              const batch = approvedBatches[0]?.name;
              if (!batch) return;
              setCampaigns((s) => [
                ...s,
                {
                  name: "Campaign " + (s.length + 1),
                  batch,
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
                      {approvedBatches.map((b) => (
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
                        onClick={(e) => {
                          e.stopPropagation();
                          setCampaigns((s) =>
                            s.map((c, i) => (i === ci ? { ...c, status: "Live" } : c))
                          );
                          toast(cp.name + " launched · sending to " + cp.batch);
                        }}
                      >
                        Send campaign
                      </button>
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

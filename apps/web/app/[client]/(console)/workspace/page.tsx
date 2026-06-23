"use client";
import { Fragment, type ReactNode, useContext, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import Link from "next/link";
import { useParams } from "next/navigation";
import clsx from "clsx";
import { Sample } from "@/components/Sample";
import { Modal } from "@/components/Modal";
import { TopbarSlotCtx } from "@/components/console/ConsoleShell";
import { useToast } from "@/components/Toast";
import { CampaignTab } from "./CampaignTab";
import { type ExclRow, type RowError, mergeExclusionText, parseExclusionCsv } from "@/lib/csv";
import { slugToTitle } from "@/lib/client";
import {
  type CompanyApi,
  type CompanyEnrichment,
  type IcpApi,
  type IcpSuggestion,
  type ProspectApi,
  type ResearchJob,
  type ResearchSpecResult,
  type ScopingPrompt,
  type FitPrompt,
  type SourcingDocList,
  addCompany,
  addProspect,
  createIcp as apiCreateIcp,
  deleteIcp as apiDeleteIcp,
  enrichProspects,
  findCompanies,
  findLookalikes,
  rescoreCompanies,
  rescoreProspects,
  updateCompanyFields,
  findPeople,
  getBrief,
  getResearchSpec,
  getStructureStatus,
  getScopingPrompt,
  getFitPrompt,
  getSourcingDocs,
  saveScopingSystemPrompt,
  listCompanies,
  listIcps,
  listProspects,
  putBrief,
  selectCompanies,
  saveSourcingDoc,
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
// `locked` = the sendout batch has been confirmed for this campaign. A freshly created
// campaign is an unlocked draft until the operator picks a batch and confirms it.
type Campaign = {
  name: string;
  batch: string;
  locked: boolean;
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
  ["summaries", "Meeting Recaps"],
  ["billing", "Billing Ledger"],
] as const;

// Live prospect pipeline statuses (string, not enum, on the API side). Two-stage flow:
// found (sourced + scored, unenriched) → confirmed (chosen to enrich) → scored (enriched + scored).
// Status is rendered as a colored dot + label + meta line (see the `.st` styles), so only the
// label map is needed here; the dot color is derived from the status in the row render.
const STATUS_LABEL: Record<string, string> = {
  scored: "Enriched",
  found: "Found",
  confirmed: "To enrich",
  new: "New",
  pushed: "Pushed",
  pending_review: "Pending review",
  accepted: "Accepted",
  gated: "Gated",
  suppressed: "Suppressed",
  score_error: "Score error",
  enrich_failed: "No match",
};
// Origin chip (not transport): where the row came from. (clay/ai_loop are legacy values still
// shown on pre-Apollo rows in dev; new rows are apollo | manual.)
const SOURCE_CLS: Record<string, string> = {
  apollo: "badge-info",
  manual: "badge-warn",
  clay: "badge-neutral",
  ai_loop: "badge-info",
};
const SOURCE_LABEL: Record<string, string> = {
  apollo: "Apollo",
  manual: "Manual",
  clay: "Clay",
  ai_loop: "AI",
};
// People that still need enrichment (no verified email yet) vs. enriched-and-ready-to-batch.
const NEEDS_ENRICH = new Set(["found", "confirmed", "score_error"]);
const ENRICHED_STATUS = "scored";
const BATCH_STATUS_CLS: Record<string, string> = {
  Approved: "badge-ok",
  Rejected: "badge-danger",
  Pending: "badge-warn",
};

// Per-prospect enrichment shown in the expanded Approval Batches table (mock — wired in Phase C/E).
// Mirrors the columns an external sourcing tool surfaces: a fit score (grade · intent heat),
// the prospect's industry, and which of the client's people they're connected to.
const SCORE_TIERS = [
  { grade: "A", heat: "Burning", cls: "badge-ok" },
  { grade: "B", heat: "Warm", cls: "badge-warn" },
  { grade: "C", heat: "Cool", cls: "badge-neutral" },
] as const;
const SAMPLE_INDUSTRIES = [
  "Artificial Intelligence",
  "Software",
  "Fintech",
  "Logistics",
  "Healthtech",
  "Retail",
  "Manufacturing",
  "Media",
];
const SAMPLE_CONNECTIONS = [
  "Sam Blond",
  "Malay Desai",
  "Shek Viswanathan",
  "Tommy Hung",
  "Stan Rapp",
];
const STAFF_ROLES = [
  "VP Sales",
  "Head of Ops",
  "RevOps Lead",
  "COO",
  "Marketing Dir.",
  "CTO",
  "Procurement",
];

type LedgerRow = {
  outcome: string;
  outcomeBadge: string;
  feedback: string;
  billing: string;
  billingBadge: string;
};
// Locked pricing constant (USD) — backend-development-plan §6.11 / §7. Supersedes the old
// HKD 6,000 + HKD 4,000 model. The rate is a fixed business rule, not per-client data.
const PER_MEETING_USD = 500;
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
// Quiet em-dash for an empty value (NOT the hatched `.ph` sample marker — a data field that
// the AI left blank is a normal state, so it reads as a muted dash, not a placeholder box).
function Dash() {
  return <span className="muted">—</span>;
}
function SpecChips({ items, warn }: { items?: string[]; warn?: boolean }) {
  if (!items || !items.length) return <Dash />;
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

// One labeled cell in the spec-review grid (reuses the .icp-cell grammar). Value is any JSX.
function SpecCell({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="icp-cell">
      <div className="k">{label}</div>
      <div className="v">{children}</div>
    </div>
  );
}
// A section heading above each spec-review grid. Deliberately heavier/darker than the faint
// `.icp-cell .k` field labels so the two tiers read as a clear hierarchy, with a hairline rule.
function SpecHead({ children }: { children: ReactNode }) {
  return (
    <div
      style={{
        margin: "20px 0 8px",
        fontSize: 12,
        fontWeight: 700,
        letterSpacing: "0.05em",
        textTransform: "uppercase",
        color: "var(--ink-soft)",
      }}
    >
      {children}
    </div>
  );
}
type Range = { min?: number | null; max?: number | null } | undefined;
// "50–500" / "50+" / "up to 500" / null, with an optional value formatter (e.g. USD).
function rangeText(r: Range, fmt: (n: number) => string = (n) => `${n}`): string | null {
  const lo = r?.min,
    hi = r?.max;
  if (lo != null && hi != null) return `${fmt(lo)}–${fmt(hi)}`;
  if (lo != null) return `${fmt(lo)}+`;
  if (hi != null) return `up to ${fmt(hi)}`;
  return null;
}
const usd = (n: number) => "$" + n.toLocaleString("en-US");
// Apollo employee ranges are comma-strings ("10,100"); show them as a readable band ("10–100").
const empBand = (r: string) => {
  const [lo, hi] = (r ?? "").split(",").map((x) => x.trim());
  if (!lo) return "";
  return hi ? `${lo}–${hi}` : `${lo}+`;
};
// A YYYY-MM-DD min/max window → "2025-12-22 → 2026-06-22" / "from …" / "until …" / null.
function dateRange(r?: { min?: string | null; max?: string | null }): string | null {
  const lo = r?.min,
    hi = r?.max;
  if (lo && hi) return `${lo} → ${hi}`;
  if (lo) return `from ${lo}`;
  if (hi) return `until ${hi}`;
  return null;
}
// A plain text value, or the quiet muted dash when empty (0 and false are real values).
function Val({ children }: { children: ReactNode }) {
  return children == null || children === "" ? <Dash /> : <>{children}</>;
}

// AI Score cell — a clean fit chip (4 tier colors) + a hover/focus info tooltip carrying the
// "why a fit" reason. Reason is rendered as JSX text (never innerHTML).
const FIT_CHIP: Record<string, string> = {
  Strong: "fit-chip--strong",
  Good: "fit-chip--good",
  Moderate: "fit-chip--moderate",
  Below: "fit-chip--below",
};
function FitScore({
  tier,
  score,
  reason,
}: {
  tier: string | null;
  score?: number | null;
  reason?: string;
}) {
  // The reason popup is fixed-positioned and portaled to <body>: the table body now scrolls
  // (overflow:auto on .list-scroll), which would clip an in-flow absolute tooltip. We compute the
  // anchor rect on hover/focus and place the popup centered above the icon, clamped to the viewport.
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);
  // Unscored row: scoring is on-demand (Update AI Score), so show a clear "Pending" rather than a dash.
  if (!tier) return <span className="muted">Pending</span>;
  const openTip = (e: { currentTarget: HTMLElement }) => {
    const r = e.currentTarget.getBoundingClientRect();
    const x = Math.min(Math.max(r.left + r.width / 2, 116), window.innerWidth - 116);
    setTip({ x, y: r.top - 10 });
  };
  return (
    <span className="fit-ai">
      <span className={clsx("fit-chip", FIT_CHIP[tier] ?? "fit-chip--below")}>
        {tier}
        {score != null ? ` · ${score}` : ""}
      </span>
      {reason ? (
        <span
          className="fit-tip"
          tabIndex={0}
          onMouseEnter={openTip}
          onFocus={openTip}
          onMouseLeave={() => setTip(null)}
          onBlur={() => setTip(null)}
        >
          <span className="fit-i">i</span>
          {tip
            ? createPortal(
                <span className="fit-pop" role="tooltip" style={{ left: tip.x, top: tip.y }}>
                  {reason}
                </span>,
                document.body,
              )
            : null}
        </span>
      ) : null}
    </span>
  );
}

// Compact currency / growth formatters for the Enrichment cell.
function fmtRevenue(n: number | null): string {
  if (!n || n <= 0) return "";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
}
function fmtGrowth(f: number | null): string {
  if (f == null) return "";
  const pct = f * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

// Enrichment cell — the 8 Apollo-enrich study fields. The cell shows a compact, truncated view;
// hovering/focusing it opens a portaled popup with the FULL untruncated content (the popup is
// fixed-positioned + portaled to <body> so the scrolling table body never clips it). It flips above
// the row when the row sits in the lower half of the viewport. All values are JSX text, no innerHTML.
function CompanyStudy({ e }: { e: CompanyEnrichment }) {
  const [tip, setTip] = useState<{
    x: number;
    y: number;
    up: boolean;
    maxH: number;
    w: number;
  } | null>(null);
  const closeTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const facts = [
    e.founded_year ? `Est. ${e.founded_year}` : "",
    fmtRevenue(e.annual_revenue),
    e.headcount_growth_12mo != null ? `${fmtGrowth(e.headcount_growth_12mo)} 12mo` : "",
  ].filter(Boolean);
  const compact = (label: string, items: string[], max: number) =>
    items.length ? (
      <div className="cstudy-line">
        <span className="cstudy-k">{label}</span> {items.slice(0, max).join(", ")}
        {items.length > max ? ` +${items.length - max}` : ""}
      </div>
    ) : null;
  const full = (label: string, items: string[]) =>
    items.length ? (
      <div className="csp-row">
        <span className="csp-k">{label}</span>
        <span>{items.join(", ")}</span>
      </div>
    ) : null;
  const hasAny =
    e.short_description ||
    facts.length ||
    e.industries.length ||
    e.technologies.length ||
    e.keywords.length ||
    e.hq;
  if (!hasAny) return <span className="muted">—</span>;

  // Open the popup sized + placed to fit the viewport: pick whichever side (below / above the row)
  // has more room, cap the height to that room (popup scrolls if content is taller), and clamp the
  // width to the screen. Solves the "popup runs off the bottom and the content is unreachable" case.
  const openTip = (ev: { currentTarget: HTMLElement }) => {
    if (closeTimer.current) clearTimeout(closeTimer.current);
    const r = ev.currentTarget.getBoundingClientRect();
    const below = window.innerHeight - r.bottom - 12;
    const above = r.top - 12;
    const up = above > below && below < 260;
    const maxH = Math.max(160, (up ? above : below) - 6);
    const w = Math.min(460, window.innerWidth - 24);
    const x = Math.max(12, Math.min(r.left, window.innerWidth - w - 12));
    setTip({ x, y: up ? r.top - 6 : r.bottom + 6, up, maxH, w });
  };
  const scheduleClose = () => {
    closeTimer.current = setTimeout(() => setTip(null), 90); // bridge the cell→popup gap
  };
  return (
    <div
      className="cstudy"
      tabIndex={0}
      onMouseEnter={openTip}
      onFocus={openTip}
      onMouseLeave={scheduleClose}
      onBlur={() => setTip(null)}
    >
      {e.short_description ? <p className="cstudy-desc">{e.short_description}</p> : null}
      {facts.length ? <div className="cstudy-facts">{facts.join(" · ")}</div> : null}
      {compact("Industries", e.industries, 2)}
      {compact("Tech", e.technologies, 4)}
      {compact("Keywords", e.keywords, 4)}
      {e.hq ? (
        <div className="cstudy-line">
          <span className="cstudy-k">HQ</span> {e.hq}
        </div>
      ) : null}
      {tip
        ? createPortal(
            <div
              className={clsx("cstudy-pop", tip.up && "cstudy-pop--up")}
              role="tooltip"
              style={{ left: tip.x, top: tip.y, width: tip.w, maxHeight: tip.maxH }}
              onMouseEnter={() => closeTimer.current && clearTimeout(closeTimer.current)}
              onMouseLeave={scheduleClose}
            >
              {e.short_description ? <p className="csp-desc">{e.short_description}</p> : null}
              {facts.length ? <div className="csp-facts">{facts.join(" · ")}</div> : null}
              {full("Industries", e.industries)}
              {full("Tech", e.technologies)}
              {full("Keywords", e.keywords)}
              {e.hq ? (
                <div className="csp-row">
                  <span className="csp-k">HQ</span>
                  <span>{e.hq}</span>
                </div>
              ) : null}
            </div>,
            document.body,
          )
        : null}
    </div>
  );
}

// Clickable company website — links to the raw URL when known, else derives one from the domain.
// Both are user/CSV-sourced strings, so render the label as JSX text and force a safe scheme.
function WebLink({ website, domain }: { website?: string; domain?: string }) {
  const label = website || domain || "";
  if (!label) return <span className="muted">—</span>;
  const href = /^https?:\/\//i.test(label) ? label : `https://${label.replace(/^\/+/, "")}`;
  return (
    <a className="weblink" href={href} target="_blank" rel="noopener noreferrer">
      {label} ↗
    </a>
  );
}

// LinkedIn glyph link for a person; nothing rendered when no profile is known.
function LinkedInLink({ url }: { url?: string }) {
  if (!url) return <span className="muted">—</span>;
  const href = /^https?:\/\//i.test(url) ? url : `https://${url.replace(/^\/+/, "")}`;
  return (
    <a className="li-ico" href={href} target="_blank" rel="noopener noreferrer" aria-label="LinkedIn">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">
        <path d="M20.45 20.45h-3.56v-5.57c0-1.33-.02-3.04-1.85-3.04-1.85 0-2.13 1.45-2.13 2.94v5.67H9.35V9h3.41v1.56h.05c.48-.9 1.64-1.85 3.37-1.85 3.6 0 4.27 2.37 4.27 5.45v6.29zM5.34 7.43a2.06 2.06 0 1 1 0-4.13 2.06 2.06 0 0 1 0 4.13zM7.12 20.45H3.56V9h3.56v11.45zM22.22 0H1.77C.79 0 0 .77 0 1.73v20.54C0 23.23.79 24 1.77 24h20.45c.98 0 1.78-.77 1.78-1.73V1.73C24 .77 23.2 0 22.22 0z" />
      </svg>
    </a>
  );
}

// The LLM-generated ResearchSpec, rendered for operator review with existing classes only.
// Always rendered: the Structure/Re-structure control lives in this panel's header, so the
// first spec is generated from here too. Before any spec exists, an empty state is shown.
function SpecReview({
  client,
  spec,
  structuring,
  saving,
  ready,
  onStructure,
  onAcceptIcp,
}: {
  client: string;
  spec: ResearchSpecResult | null;
  structuring: boolean;
  saving: boolean;
  ready: boolean;
  onStructure: () => void;
  onAcceptIcp: (s: IcpSuggestion) => void;
}) {
  // Prompt popup: the System prompt (left) is editable + saved per client; the Input prompt
  // (right) is read-only — it is always the client brief + ICPs.
  const [promptOpen, setPromptOpen] = useState(false);
  const [prompt, setPrompt] = useState<ScopingPrompt | null>(null);
  const [promptErr, setPromptErr] = useState<string | null>(null);
  const [promptLoading, setPromptLoading] = useState(false);
  const [systemDraft, setSystemDraft] = useState("");
  const [isCustom, setIsCustom] = useState(false);
  const [savingPrompt, setSavingPrompt] = useState(false);
  const [saveMsg, setSaveMsg] = useState<string | null>(null);
  async function openPrompt() {
    setPromptOpen(true);
    setPromptLoading(true);
    setPromptErr(null);
    setSaveMsg(null);
    try {
      const p = await getScopingPrompt(client);
      setPrompt(p);
      setSystemDraft(p.system);
      setIsCustom(p.system_is_custom);
    } catch (e) {
      setPromptErr(e instanceof Error ? e.message : "Could not load the prompt");
    } finally {
      setPromptLoading(false);
    }
  }
  async function saveSystemPrompt() {
    setSavingPrompt(true);
    setSaveMsg(null);
    try {
      const r = await saveScopingSystemPrompt(client, systemDraft);
      setSystemDraft(r.system);
      setIsCustom(r.is_custom);
      setSaveMsg(r.is_custom ? "Saved" : "Reset to default");
      setTimeout(() => setSaveMsg(null), 1600);
    } catch (e) {
      setSaveMsg(e instanceof Error ? e.message : "Save failed");
    } finally {
      setSavingPrompt(false);
    }
  }
  // The full v3 ResearchSpec shape — exact Apollo request fields, rendered field-by-field so the
  // operator can review every parameter the LLM produced before Phase C's Apollo search (see
  // research_spec.py). `intent_filters` carries buying signals; `icp_validation` the paying-customer
  // read; `credit_policy` is server-set, not AI.
  const s = (spec?.spec ?? {}) as {
    company_search_params?: {
      q_organization_keyword_tags?: string[];
      organization_num_employees_ranges?: string[];
      organization_locations?: string[];
      revenue_range?: Range;
    };
    people_search_params?: {
      person_titles?: string[];
      include_similar_titles?: boolean;
      q_keywords?: string;
      person_seniorities?: string[];
      organization_locations?: string[];
      organization_num_employees_ranges?: string[];
    };
    intent_filters?: {
      company?: {
        latest_funding_date_range?: { min?: string | null; max?: string | null };
        q_organization_job_titles?: string[];
        organization_job_posted_at_range?: { min?: string | null; max?: string | null };
      };
      recency_window?: { funding_since?: string | null; jobs_posted_since?: string | null };
    };
    icp_validation?: {
      customer_profiles?: {
        name?: string;
        domain?: string;
        industry?: string;
        employee_band?: string;
        hq_country?: string;
        business_model?: string;
        source?: string;
        confidence?: string;
      }[];
      paying_customer_summary?: string;
    };
    credit_policy?: {
      email_status_filter?: string[];
      phone?: boolean;
      max_companies?: number;
      max_people?: number;
    };
  };
  const cs = s.company_search_params ?? {};
  const ppl = s.people_search_params ?? {};
  const intent = s.intent_filters?.company ?? {};
  const recency = s.intent_filters?.recency_window ?? {};
  const val = s.icp_validation ?? {};
  const profiles = val.customer_profiles ?? [];
  const cp = s.credit_policy ?? {};
  const blocked = structuring || saving || !ready;
  return (
    <>
    <div className="panel" style={{ marginTop: 18 }}>
      <div className="panel-head">
        <div>
          <h3>Prospect Scope</h3>
          <div className="ph-sub">
            Complete all 6 sections of the brief first. We summarize the full brief to source
            prospects.
          </div>
        </div>
        <div style={{ display: "flex", flexDirection: "column", alignItems: "flex-end", gap: 5 }}>
          <div className="row" style={{ gap: 8 }}>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              title="Show the exact system + input prompt sent to the AI to generate this scope."
              onClick={openPrompt}
            >
              View prompt
            </button>
            {/* The span carries the tooltip; the disabled button gets pointer-events:none so the
                hover falls through to the span and the title shows (disabled buttons swallow it). */}
            <span
              style={{ display: "inline-flex" }}
              title={
                !ready
                  ? "Complete all 6 sections of the brief first. We summarize the full brief to source prospects."
                  : "Summarize this brief with AI into a prospect scope."
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
          {/* Time-demand note: scoping runs DeepSeek V4 Pro (deep reasoning + web search) on a
              background worker, so it takes ~1 min — but the user is never blocked while it runs.
              Shown only while a run is in flight; hidden once it completes. */}
          {structuring && (
            <div
              className="ph-sub"
              style={{ fontSize: 11.5, textAlign: "right", whiteSpace: "nowrap" }}
            >
              ⏱ Generating… ~1 min · runs in the background, keep working
            </div>
          )}
        </div>
      </div>
      {!spec ? (
        <div className="panel-pad">
          <div className="sum-empty">
            Not generated yet · fill in the brief, then generate your Apollo-ready scope.
          </div>
        </div>
      ) : (
        <div className="panel-pad">
          <SpecHead>Company search · firmographics</SpecHead>
          <div className="icp-grid">
            <SpecCell label="Industry keyword tags">
              <SpecChips items={cs.q_organization_keyword_tags} />
            </SpecCell>
            <SpecCell label="Company size">
              <SpecChips items={(cs.organization_num_employees_ranges ?? []).map(empBand)} />
            </SpecCell>
            <SpecCell label="Locations (HQ)">
              <SpecChips items={cs.organization_locations} />
            </SpecCell>
            <SpecCell label="Revenue (USD)">
              <Val>{rangeText(cs.revenue_range, usd)}</Val>
            </SpecCell>
          </div>

          <SpecHead>People search · personas</SpecHead>
          <div className="icp-grid">
            <SpecCell label="Target titles">
              <SpecChips items={ppl.person_titles} />
            </SpecCell>
            <SpecCell label="Similar titles">
              {ppl.person_titles?.length ? (
                ppl.include_similar_titles ? (
                  "Included"
                ) : (
                  "Exact only"
                )
              ) : (
                <Dash />
              )}
            </SpecCell>
            <SpecCell label="Industry keywords">
              <Val>{ppl.q_keywords}</Val>
            </SpecCell>
            <SpecCell label="Seniority">
              <SpecChips items={ppl.person_seniorities} />
            </SpecCell>
            <SpecCell label="Locations (HQ)">
              <SpecChips items={ppl.organization_locations} />
            </SpecCell>
            <SpecCell label="Company size">
              <SpecChips items={(ppl.organization_num_employees_ranges ?? []).map(empBand)} />
            </SpecCell>
          </div>

          <SpecHead>Intent signals · funding &amp; hiring</SpecHead>
          <div className="icp-grid">
            <SpecCell label="Funding closed">
              <Val>{dateRange(intent.latest_funding_date_range)}</Val>
            </SpecCell>
            <SpecCell label="Funding since">
              <Val>{recency.funding_since}</Val>
            </SpecCell>
            <SpecCell label="Hiring for">
              <SpecChips items={intent.q_organization_job_titles} />
            </SpecCell>
            <SpecCell label="Roles posted">
              <Val>{dateRange(intent.organization_job_posted_at_range)}</Val>
            </SpecCell>
            <SpecCell label="Jobs posted since">
              <Val>{recency.jobs_posted_since}</Val>
            </SpecCell>
          </div>

          <SpecHead>ICP validation · who actually pays</SpecHead>
          <div className="icp-grid">
            <SpecCell label="Paying-customer summary">
              <Val>{val.paying_customer_summary}</Val>
            </SpecCell>
          </div>
          {profiles.map((c, i) => (
            <div className="icp-grid" key={i} style={{ marginTop: 8 }}>
              <SpecCell label="Customer">
                <Val>{c.name || c.domain}</Val>
              </SpecCell>
              <SpecCell label="Industry">
                <Val>{c.industry}</Val>
              </SpecCell>
              <SpecCell label="Size">
                <Val>{c.employee_band}</Val>
              </SpecCell>
              <SpecCell label="HQ">
                <Val>{c.hq_country}</Val>
              </SpecCell>
              <SpecCell label="Model">
                <Val>{c.business_model}</Val>
              </SpecCell>
              <SpecCell label="Source">
                {c.source ? (
                  <span className={"badge badge-" + (c.source === "web" ? "info" : "neutral")}>
                    {c.source}
                    {c.confidence ? ` · ${c.confidence}` : ""}
                  </span>
                ) : (
                  <Dash />
                )}
              </SpecCell>
            </div>
          ))}

          <SpecHead>Credit policy · server-set (not AI)</SpecHead>
          <div className="icp-grid">
            <SpecCell label="Email status">
              <SpecChips items={cp.email_status_filter} />
            </SpecCell>
            <SpecCell label="Phone enrich">{cp.phone ? "On" : "Off"}</SpecCell>
            <SpecCell label="Max companies">
              <Val>{cp.max_companies}</Val>
            </SpecCell>
            <SpecCell label="Max people">
              <Val>{cp.max_people}</Val>
            </SpecCell>
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
              {(sug.evidencing_customers?.length ?? 0) > 0 && (
                <div className="is-row">
                  <span className="k">Based on</span>
                  <SpecChips items={sug.evidencing_customers ?? []} />
                </div>
              )}
              {(sug.company_search_params?.q_organization_keyword_tags?.length ?? 0) > 0 && (
                <div className="is-row">
                  <span className="k">Industries</span>
                  <SpecChips items={sug.company_search_params?.q_organization_keyword_tags ?? []} />
                </div>
              )}
              {(sug.people_search_params?.person_titles?.length ?? 0) > 0 && (
                <div className="is-row">
                  <span className="k">Titles</span>
                  <SpecChips items={sug.people_search_params?.person_titles ?? []} />
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </div>

      <Modal
        open={promptOpen}
        onClose={() => setPromptOpen(false)}
        title="AI scoping prompt"
        subtitle="The exact system + input prompt sent to the model to generate the prospect scope."
        className="modal-lg"
        footer={
          <button className="btn btn-primary btn-sm" onClick={() => setPromptOpen(false)}>
            Done
          </button>
        }
      >
        {promptLoading ? (
          <div className="sum-empty">Loading prompt…</div>
        ) : promptErr ? (
          <div className="sum-empty">{promptErr}</div>
        ) : prompt ? (
          <>
            <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
              <span className="badge badge-info">model · {prompt.model.join(" → ")}</span>
              <span className="badge badge-neutral">purpose · {prompt.purpose}</span>
              <span className="badge badge-neutral">{prompt.prompt_version}</span>
            </div>
            <div className="prompt-cols">
              {/* LEFT — System prompt: editable + Save (adjust for testing; saved per client). */}
              <div className="prompt-col">
                <div className="prompt-col-head">
                  <label>
                    System prompt{" "}
                    <span className={"badge badge-" + (isCustom ? "warn" : "neutral")}>
                      {isCustom ? "custom" : "default"}
                    </span>
                  </label>
                  <div className="row" style={{ gap: 8, alignItems: "center" }}>
                    {saveMsg && <span className="ph-sub">{saveMsg}</span>}
                    <button
                      type="button"
                      className="btn btn-accent btn-xs"
                      disabled={savingPrompt || systemDraft === prompt.system}
                      onClick={saveSystemPrompt}
                    >
                      {savingPrompt ? "Saving…" : "Save"}
                    </button>
                  </div>
                </div>
                <textarea
                  className="prompt-edit"
                  value={systemDraft}
                  spellCheck={false}
                  onChange={(e) => setSystemDraft(e.target.value)}
                />
              </div>
              {/* RIGHT — Input prompt: read-only, always the client brief + ICPs. */}
              <div className="prompt-col">
                <div className="prompt-col-head">
                  <label>Input prompt</label>
                  <span className="ph-sub">read-only · from client brief</span>
                </div>
                <pre className="prompt-pre">{prompt.user}</pre>
              </div>
            </div>
            <div className="ph-sub prompt-hint">
              Edits are saved for this client and used on the next Generate Scope. Save the default
              text to reset.
            </div>
          </>
        ) : null}
      </Modal>
    </>
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

// Do-not-contact list — the three exclusion sources from the Brief. Everyone here is
// suppressed from every batch and campaign; it is pinned to the top of Approval Batches
// for review and never overlaps a sendout batch.
// Each entry mirrors the Brief exclusion input format: company domain · company name · website.
const EXCLUSIONS: {
  label: string;
  tag: string;
  cls: string;
  entries: ExclRow[];
}[] = [
  {
    label: "Existing customers to exclude",
    tag: "Customer",
    cls: "badge-info",
    entries: [
      { domain: "acme.com", name: "Acme Corp", website: "https://acme.com" },
      { domain: "globex.com", name: "Globex Inc", website: "https://globex.com" },
      { domain: "initech.com", name: "Initech", website: "https://initech.com" },
    ],
  },
  {
    label: "Active deals / pipeline to exclude",
    tag: "Active deal",
    cls: "badge-warn",
    entries: [
      { domain: "umbrella.co", name: "Umbrella Co", website: "https://umbrella.co" },
      { domain: "soylent.com", name: "Soylent Ltd", website: "https://soylent.com" },
    ],
  },
  {
    label: "Competitors & do-not-contact (any reason)",
    tag: "Competitor / DNC",
    cls: "badge-danger",
    entries: [
      { domain: "competitor-a.com", name: "Competitor A", website: "https://competitor-a.com" },
      { domain: "competitor-b.io", name: "Competitor B", website: "https://competitor-b.io" },
      { domain: "hooli.com", name: "Hooli", website: "https://hooli.com" },
    ],
  },
];
const EXCLUSION_COUNT = EXCLUSIONS.reduce((n, g) => n + g.entries.length, 0);

// ---- Find-company scope override (Settings modal) -----------------------------------------
// A manual override of the AI scope's Apollo company-search filters, persisted per client in
// localStorage and passed verbatim to find-company. `null` = use the saved spec unchanged.
type ScopeOverride = {
  company_search_params: Record<string, unknown>;
  intent_filters: Record<string, unknown>;
};
// The editable shape — arrays are held as comma/semicolon text so they type naturally in inputs.
type ScopeForm = {
  keywords: string;
  sizes: string;
  locations: string;
  revenueMin: string;
  revenueMax: string;
  hiringTitles: string;
  fundedMin: string;
  fundedMax: string;
  jobsMin: string;
  jobsMax: string;
};
const SCOPE_KEY = (client: string) => `holdslot_scope_${client}`;
function loadScopeOverride(client: string): ScopeOverride | null {
  if (typeof window === "undefined") return null;
  try {
    const v = JSON.parse(localStorage.getItem(SCOPE_KEY(client)) || "null");
    return v && typeof v === "object" ? (v as ScopeOverride) : null;
  } catch {
    return null;
  }
}
function saveScopeOverride(client: string, v: ScopeOverride | null) {
  if (typeof window === "undefined") return;
  try {
    if (v) localStorage.setItem(SCOPE_KEY(client), JSON.stringify(v));
    else localStorage.removeItem(SCOPE_KEY(client));
  } catch {
    /* ignore */
  }
}
const csvToArr = (s: string) =>
  s
    .split(",")
    .map((x) => x.trim())
    .filter(Boolean);
const semiToArr = (s: string) =>
  s
    .split(";")
    .map((x) => x.trim())
    .filter(Boolean);
const arrToCsv = (a: unknown) => (Array.isArray(a) ? (a as string[]).join(", ") : "");

// The scope find-company would use right now: the manual override if set, else the AI spec's blocks.
function effectiveScope(
  override: ScopeOverride | null,
  spec: ResearchSpecResult | null
): ScopeOverride {
  if (override) return override;
  const sp = (spec?.spec ?? {}) as {
    company_search_params?: Record<string, unknown>;
    intent_filters?: Record<string, unknown>;
  };
  return {
    company_search_params: sp.company_search_params ?? {},
    intent_filters: sp.intent_filters ?? {},
  };
}
function scopeToForm(o: ScopeOverride): ScopeForm {
  const cs = (o.company_search_params ?? {}) as Record<string, unknown>;
  const c = ((o.intent_filters as { company?: Record<string, unknown> })?.company ?? {}) as Record<
    string,
    unknown
  >;
  const rev = (cs.revenue_range ?? {}) as { min?: number | null; max?: number | null };
  const fund = (c.latest_funding_date_range ?? {}) as { min?: string | null; max?: string | null };
  const jobs = (c.organization_job_posted_at_range ?? {}) as {
    min?: string | null;
    max?: string | null;
  };
  return {
    keywords: arrToCsv(cs.q_organization_keyword_tags),
    sizes: Array.isArray(cs.organization_num_employees_ranges)
      ? (cs.organization_num_employees_ranges as string[]).join("; ")
      : "",
    locations: arrToCsv(cs.organization_locations),
    revenueMin: rev.min != null ? String(rev.min) : "",
    revenueMax: rev.max != null ? String(rev.max) : "",
    hiringTitles: arrToCsv(c.q_organization_job_titles),
    fundedMin: fund.min ?? "",
    fundedMax: fund.max ?? "",
    jobsMin: jobs.min ?? "",
    jobsMax: jobs.max ?? "",
  };
}
function formToOverride(f: ScopeForm): ScopeOverride {
  return {
    company_search_params: {
      q_organization_keyword_tags: csvToArr(f.keywords),
      organization_num_employees_ranges: semiToArr(f.sizes),
      organization_locations: csvToArr(f.locations),
      revenue_range: {
        min: f.revenueMin ? Number(f.revenueMin) : null,
        max: f.revenueMax ? Number(f.revenueMax) : null,
      },
    },
    intent_filters: {
      company: {
        q_organization_job_titles: csvToArr(f.hiringTitles),
        latest_funding_date_range: { min: f.fundedMin || null, max: f.fundedMax || null },
        organization_job_posted_at_range: { min: f.jobsMin || null, max: f.jobsMax || null },
      },
    },
  };
}
// A one-line human read of the active scope — for the empty state + the 0-results toast.
function scopeSummary(o: ScopeOverride): string {
  const cs = (o.company_search_params ?? {}) as Record<string, unknown>;
  const c = ((o.intent_filters as { company?: Record<string, unknown> })?.company ?? {}) as Record<
    string,
    unknown
  >;
  const arr = (v: unknown) => (Array.isArray(v) ? (v as string[]) : []);
  const fund = (c.latest_funding_date_range ?? {}) as { min?: string | null; max?: string | null };
  const jobs = (c.organization_job_posted_at_range ?? {}) as {
    min?: string | null;
    max?: string | null;
  };
  const parts: string[] = [];
  if (arr(cs.organization_locations).length) parts.push(arr(cs.organization_locations).join("/"));
  if (arr(cs.q_organization_keyword_tags).length)
    parts.push(arr(cs.q_organization_keyword_tags).join("/"));
  if (arr(cs.organization_num_employees_ranges).length)
    parts.push(`size ${arr(cs.organization_num_employees_ranges).join(", ")}`);
  if (fund.min || fund.max) parts.push("recently funded");
  if (arr(c.q_organization_job_titles).length)
    parts.push(`hiring ${arr(c.q_organization_job_titles).join("/")}`);
  if (jobs.min || jobs.max) parts.push("recent job posts");
  return parts.join(" · ");
}

// ---- Find-people scope override (Step-2 Settings modal) -----------------------------------
// Same pattern as the company scope: a per-client manual override of the AI scope's Apollo
// mixed_people/api_search filters. `organization_ids` is NOT here — the server sets it per selected
// org. `null` → use the saved spec's people_search_params.
type PeopleScopeOverride = { people_search_params: Record<string, unknown> };
type PeopleScopeForm = {
  titles: string;
  similar: boolean;
  seniorities: string;
  keywords: string;
  locations: string;
  sizes: string;
};
const PPL_SCOPE_KEY = (client: string) => `holdslot_pplscope_${client}`;
function loadPeopleScopeOverride(client: string): PeopleScopeOverride | null {
  if (typeof window === "undefined") return null;
  try {
    const v = JSON.parse(localStorage.getItem(PPL_SCOPE_KEY(client)) || "null");
    return v && typeof v === "object" ? (v as PeopleScopeOverride) : null;
  } catch {
    return null;
  }
}
function savePeopleScopeOverride(client: string, v: PeopleScopeOverride | null) {
  if (typeof window === "undefined") return;
  try {
    if (v) localStorage.setItem(PPL_SCOPE_KEY(client), JSON.stringify(v));
    else localStorage.removeItem(PPL_SCOPE_KEY(client));
  } catch {
    /* ignore */
  }
}
function effectivePeopleScope(
  override: PeopleScopeOverride | null,
  spec: ResearchSpecResult | null
): PeopleScopeOverride {
  if (override) return override;
  const sp = (spec?.spec ?? {}) as { people_search_params?: Record<string, unknown> };
  return { people_search_params: sp.people_search_params ?? {} };
}
function peopleScopeToForm(o: PeopleScopeOverride): PeopleScopeForm {
  const ps = (o.people_search_params ?? {}) as Record<string, unknown>;
  return {
    titles: arrToCsv(ps.person_titles),
    similar: ps.include_similar_titles === true,
    seniorities: arrToCsv(ps.person_seniorities),
    keywords: typeof ps.q_keywords === "string" ? ps.q_keywords : "",
    locations: arrToCsv(ps.organization_locations),
    sizes: Array.isArray(ps.organization_num_employees_ranges)
      ? (ps.organization_num_employees_ranges as string[]).join("; ")
      : "",
  };
}
function formToPeopleOverride(f: PeopleScopeForm): PeopleScopeOverride {
  return {
    people_search_params: {
      person_titles: csvToArr(f.titles),
      include_similar_titles: f.similar,
      person_seniorities: csvToArr(f.seniorities),
      q_keywords: f.keywords.trim(),
      organization_locations: csvToArr(f.locations),
      organization_num_employees_ranges: semiToArr(f.sizes),
    },
  };
}
function peopleScopeSummary(o: PeopleScopeOverride): string {
  const ps = (o.people_search_params ?? {}) as Record<string, unknown>;
  const arr = (v: unknown) => (Array.isArray(v) ? (v as string[]) : []);
  const parts: string[] = [];
  if (arr(ps.person_titles).length)
    parts.push(
      `${arr(ps.person_titles).join("/")}${ps.include_similar_titles ? " (+similar)" : ""}`
    );
  if (arr(ps.person_seniorities).length) parts.push(arr(ps.person_seniorities).join("/"));
  if (typeof ps.q_keywords === "string" && ps.q_keywords.trim())
    parts.push(`“${ps.q_keywords.trim()}”`);
  if (arr(ps.organization_locations).length) parts.push(arr(ps.organization_locations).join("/"));
  return parts.join(" · ");
}

export default function Workspace() {
  const { client } = useParams<{ client: string }>();
  const clientName = slugToTitle(client);
  const toast = useToast();
  // The tab bar renders into the console topbar (replacing the breadcrumb) via this slot.
  const tabSlot = useContext(TopbarSlotCtx);

  const [tab, setTab] = useState<string>("brief");
  // Keep the rendered tab in sync with the URL hash in BOTH directions: on mount/deep-link and
  // whenever the hash changes via Back/Forward (popstate) — Next's client router doesn't fire
  // hashchange on its own, so without the listener the Back button desyncs URL from view.
  useEffect(() => {
    const sync = () => {
      const h = location.hash.slice(1);
      if (TABS.some(([k]) => k === h)) setTab(h);
    };
    sync();
    window.addEventListener("popstate", sync);
    window.addEventListener("hashchange", sync);
    return () => {
      window.removeEventListener("popstate", sync);
      window.removeEventListener("hashchange", sync);
    };
  }, []);
  function activate(name: string) {
    setTab(name);
    // pushState (not replace) so each tab is a real history entry the Back button can return to.
    if (location.hash.slice(1) !== name) history.pushState(null, "", "#" + name);
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
            industries: sug.company_search_params?.q_organization_keyword_tags ?? [],
            jobTitles: sug.people_search_params?.person_titles ?? [],
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
  // Called from an inline arrow at each <input> (not curried in JSX) so it's recognised as an
  // event handler — letting persist() read its refs without a refs-during-render warning.
  const onCsv = async (
    key: "customers" | "deals" | "doNotContact",
    e: React.ChangeEvent<HTMLInputElement>
  ) => {
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

  // accordion: one section open at a time (0 = all collapsed). Starts collapsed; an effect
  // auto-opens the earliest still-incomplete section once the brief hydrates (see below).
  const [openSec, setOpenSec] = useState(0);
  // True once we've auto-opened a section for the current client load (so manual toggles stick).
  const autoOpenedRef = useRef(false);
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
    autoOpenedRef.current = false; // re-pick the earliest-incomplete section for this client
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
      // Resume polling if a structuring job is still running from before this load (e.g. a refresh
      // mid-generation) — the worker runs server-side, so reattach the spinner + pick up the result.
      const job = await getStructureStatus(client).catch(() => null);
      if (alive && job && (job.status === "queued" || job.status === "running")) {
        setStructuring(true);
        pollStructuring(job, client).finally(() => {
          if (alive) setStructuring(false);
        });
      }
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

  // Poll the async structuring worker (DeepSeek V4 Pro scoping runs ~1 min off the request path)
  // to a terminal state, then load the produced spec. Shared by the Generate button + on-load
  // resume (a job can still be running after a refresh). `startClient` pins the call to the client
  // that launched it, so a mid-run client switch never writes another client's spec.
  async function pollStructuring(job: ResearchJob, startClient: string) {
    const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));
    const deadline = Date.now() + 4 * 60 * 1000; // generous cap; worker keeps running server-side
    while ((job.status === "queued" || job.status === "running") && Date.now() < deadline) {
      await sleep(3000);
      job = await getStructureStatus(startClient);
    }
    if (job.status === "done") {
      const rs = await getResearchSpec(startClient);
      setSpec(rs.latest);
      toast("Prospect scope v" + (job.spec_version ?? rs.latest?.version ?? "") + " generated");
    } else if (job.status === "error") {
      toast(job.error || "Structuring failed", "warn");
    } else {
      toast("Still generating — this can take ~1 min; it'll appear when ready.", "warn");
    }
  }

  // Save the brief + ICPs, then kick off async structuring and poll it to completion.
  async function runStructure() {
    setStructuring(true);
    try {
      await persist();
      const job = await structureBrief(client); // 202 — returns the job to poll
      await pollStructuring(job, client);
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
  // Top-bar percentage tracks required fields filled across all sections (not sections done /6),
  // so each field moves the bar rather than only a whole completed section.
  const allReq = Object.values(secReq).flat();
  const completePct = Math.round((allReq.filter(Boolean).length / allReq.length) * 100);
  // Prospect-Scope gating stays section-based (every ICP ready, not just the current one), so the
  // field-based bar above can read 100% without unblocking before all sections are truly done.
  const allComplete = Object.values(secComplete).every(Boolean);
  // The earliest section still missing required fields (0 = none — every section is complete).
  const firstIncompleteSec = ([1, 2, 3, 4, 5, 6] as const).find((n) => !secComplete[n]) ?? 0;
  // On load / client switch, open that section (or collapse all when nothing is left). Runs once
  // per load — guarded by autoOpenedRef so a later edit completing a section won't yank it shut.
  useEffect(() => {
    if (loading || autoOpenedRef.current) return;
    autoOpenedRef.current = true;
    setOpenSec(firstIncompleteSec);
  }, [loading, firstIncompleteSec]);
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
    { name: "Campaign 1", batch: "Batch 1", locked: true },
    { name: "Campaign 2", batch: "Batch 2", locked: true },
  ]);
  // Campaigns can only be linked to client-approved batches — pending/rejected
  // batches are never selectable, so a linked campaign is always safe to send.
  const approvedBatches = batches.filter((b) => b.status === "Approved");

  // Prospect list (Phase C — live). Prospects, sourcing docs, and the round-history scoreboard
  // are loaded from the API; selection is by prospect id. Batch creation stays client-side until
  // Phase D builds the backend (the select → batch seam is real; the batch object is the mock).
  const [prospects, setProspects] = useState<ProspectApi[]>([]);
  const [prospectsLoading, setProspectsLoading] = useState(false);
  const [companiesLoading, setCompaniesLoading] = useState(false);
  // Tracks the live client so an async reload/handler that resolves *after* a client switch can
  // bail before writing the previous client's data into the new client's view.
  const clientRef = useRef(client);
  const [checked, setChecked] = useState<Set<string>>(new Set());
  const [search, setSearch] = useState("");
  const [fFit, setFFit] = useState("");
  const [fIcp, setFIcp] = useState(""); // an ICP id (or "")
  const [newBatchName, setNewBatchName] = useState("");
  // Fit-rubric settings (the versioned scoring rubric), edited in a modal.
  const [showSourcing, setShowSourcing] = useState(false);
  const [docs, setDocs] = useState<SourcingDocList | null>(null);
  const [rubricDraft, setRubricDraft] = useState("");
  const [savingDoc, setSavingDoc] = useState<"fit_scoring" | null>(null);
  // The real fit-score prompt for one sample company (system rubric + the live targeting context
  // built from this client's brief + research spec + ICP docs), fetched when the modal opens.
  const [fitPrompt, setFitPrompt] = useState<FitPrompt | null>(null);
  const [fitPromptLoading, setFitPromptLoading] = useState(false);
  const [fitPromptErr, setFitPromptErr] = useState<string | null>(null);

  // Two-stage prospecting (company-first): step 1 finds companies, step 2 finds people at the
  // selected ones. `listStage` is the sub-view; companies + their selection live here.
  const [listStage, setListStage] = useState<"companies" | "people">("companies");
  const [companies, setCompanies] = useState<CompanyApi[]>([]);
  const [companyChecked, setCompanyChecked] = useState<Set<string>>(new Set());
  const [coSearch, setCoSearch] = useState("");
  const [coFit, setCoFit] = useState("");
  // Status filter: "" all · "accepted" = people_found (the Accepted tag) · "pending" = not yet.
  const [coStatus, setCoStatus] = useState("");
  const [enriching, setEnriching] = useState(false);
  const [findingCo, setFindingCo] = useState(false);
  const [updatingFields, setUpdatingFields] = useState(false);
  const [findingLookalike, setFindingLookalike] = useState(false);
  // Company rows whose AI fit-score is being computed in the background (post-Lookalike). The AI
  // Score cell shows a "Scoring…" status for these until each chunk lands.
  const [scoringCoIds, setScoringCoIds] = useState<Set<string>>(new Set());
  const [findingPpl, setFindingPpl] = useState(false);
  const [staging, setStaging] = useState(false); // Step-1 → Step-2 move in flight
  const [removing, setRemoving] = useState(false); // Step-2 → Step-1 un-stage in flight
  // Step-2 company rows whose people are being searched right now (per-row "Finding people…").
  const [findingPplIds, setFindingPplIds] = useState<Set<string>>(new Set());
  // Prospect rows whose AI fit-score is being computed in the background (Step-2 'Get AI score').
  const [scoringPersonIds, setScoringPersonIds] = useState<Set<string>>(new Set());
  // Manual-add modals (same schema as imported rows; source=manual).
  const blankCo = {
    domain: "",
    name: "",
    website: "",
    industry: "",
    size: "",
    country: "",
    linkedin_url: "",
  };
  const [addCoOpen, setAddCoOpen] = useState(false);
  const [coForm, setCoForm] = useState({ ...blankCo });
  const [savingCo, setSavingCo] = useState(false);
  // Manual override of the AI scope's Apollo company-search filters (Settings modal).
  const [scopeOverride, setScopeOverride] = useState<ScopeOverride | null>(null);
  const [scopeOpen, setScopeOpen] = useState(false);
  const [scopeForm, setScopeForm] = useState<ScopeForm | null>(null);
  // Same, for the Step-2 Apollo people-search filters.
  const [peopleScopeOverride, setPeopleScopeOverride] = useState<PeopleScopeOverride | null>(null);
  const [peopleScopeOpen, setPeopleScopeOpen] = useState(false);
  const [peopleScopeForm, setPeopleScopeForm] = useState<PeopleScopeForm | null>(null);
  const blankPerson = {
    full_name: "",
    company: "",
    domain: "",
    linkedin_url: "",
    email: "",
    title: "",
    seniority: "",
  };
  const [addPersonOpen, setAddPersonOpen] = useState(false);
  const [personForm, setPersonForm] = useState({ ...blankPerson });
  const [savingPerson, setSavingPerson] = useState(false);

  const icpNameById = useMemo(() => {
    const m = new Map<string, string>();
    for (const p of icps) if (p.id) m.set(p.id, p.short);
    return m;
  }, [icps]);

  async function reloadProspects() {
    setProspectsLoading(true);
    try {
      // Let errors propagate — a failed reload must surface, never silently blank the list
      // (which reads as "no prospects" and tempts a re-import / re-spend).
      const ps = await listProspects(client);
      if (clientRef.current !== client) return; // client switched mid-flight — drop stale data
      setProspects(ps);
      setChecked(new Set());
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh prospects", "warn");
      }
    } finally {
      if (clientRef.current === client) setProspectsLoading(false);
    }
  }

  async function reloadCompanies() {
    setCompaniesLoading(true);
    try {
      const cs = await listCompanies(client);
      if (clientRef.current !== client) return;
      setCompanies(cs);
    } catch (e) {
      if (clientRef.current === client) {
        toast(e instanceof Error ? e.message : "Couldn’t refresh companies", "warn");
      }
    } finally {
      if (clientRef.current === client) setCompaniesLoading(false);
    }
  }

  // Hydrate companies, the prospect list, and sourcing docs for this client. Selection and
  // filters are reset here — they reference the *previous* client's prospect/ICP ids and would
  // otherwise leak across a switch (a stale fIcp silently hides the new client's rows; stale
  // checked ids feed accept/createBatch). Load errors surface as a toast and never blank the
  // list silently (that reads as "no prospects" and tempts a re-import / re-spend).
  useEffect(() => {
    if (!client) return;
    clientRef.current = client;
    setChecked(new Set());
    setCompanyChecked(new Set());
    setSearch("");
    setCoSearch("");
    setFIcp("");
    setFFit("");
    setCoFit("");
    setCoStatus("");
    setScopeOverride(loadScopeOverride(client)); // per-client manual scope; null → AI spec
    setPeopleScopeOverride(loadPeopleScopeOverride(client));
    let alive = true;
    setCompaniesLoading(true);
    setProspectsLoading(true);
    (async () => {
      try {
        const [ps, cs, dl] = await Promise.all([
          listProspects(client),
          listCompanies(client),
          getSourcingDocs(client),
        ]);
        if (!alive) return;
        setProspects(ps);
        setCompanies(cs);
        setDocs(dl);
        setRubricDraft(dl?.fit_scoring?.body ?? "");
      } catch (e) {
        if (alive) toast(e instanceof Error ? e.message : "Couldn’t load prospects", "warn");
      } finally {
        if (alive) {
          setCompaniesLoading(false);
          setProspectsLoading(false);
        }
      }
    })();
    return () => {
      alive = false;
    };
  }, [client]);

  // Step 2 is company-centric: the pursued companies (staged into Step 2 as `selected`, or already
  // searched → `people_found`) are the rows; each company's found people nest beneath it. `search`
  // filters the companies; `fFit` filters the people shown within them.
  const pursued = useMemo(
    () =>
      companies.filter(
        (c) =>
          (c.status === "selected" || c.status === "people_found") &&
          (!search || `${c.name} ${c.domain}`.toLowerCase().includes(search.toLowerCase()))
      ),
    [companies, search]
  );
  // Prospects grouped by their company id (robust — the company label can drift; the id can't).
  const prospectsByCompany = useMemo(() => {
    const m = new Map<string, ProspectApi[]>();
    for (const p of prospects) {
      if (!p.company_id) continue;
      const g = m.get(p.company_id);
      if (g) g.push(p);
      else m.set(p.company_id, [p]);
    }
    return m;
  }, [prospects]);
  // Rows of a pursued company that pass the fit filter — the per-company nested list.
  const rowsForCompany = (id: string) =>
    (prospectsByCompany.get(id) ?? []).filter((p) => !fFit || p.fit_tier === fFit);
  // People in view across all pursued companies = the unit of selection for score / enrich / batch.
  const visible = useMemo(
    () => pursued.flatMap((c) => rowsForCompany(c.id)),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [pursued, prospectsByCompany, fFit]
  );
  const selCount = visible.filter((p) => checked.has(p.id)).length;
  const allChecked = visible.length > 0 && selCount === visible.length;
  // Step-2 companies that are ticked — the unit of selection for Find People.
  const pplCoSel = pursued.filter((c) => companyChecked.has(c.id));
  // Step-2 dock: enrich and batch are mutually exclusive — find before enrich, enrich before
  // batch. Computed over the WHOLE selection (not the filtered view) so a filter change can't
  // drop checked rows. `confirmEnrich`/`createBatch` re-derive from the same rule.
  const selectedProspects = useMemo(
    () => prospects.filter((p) => checked.has(p.id)),
    [prospects, checked]
  );
  const toEnrich = selectedProspects.filter((p) => NEEDS_ENRICH.has(p.status));
  const enrichedSel = selectedProspects.filter((p) => p.status === ENRICHED_STATUS);
  const canEnrich = toEnrich.length > 0;
  // Batch only once EVERY selected person is enriched (a verified email) — closes the gap where an
  // enrich_failed (no-email) row slipped through the old "nothing still needs enrich" gate.
  const canBatch =
    selectedProspects.length > 0 && selectedProspects.every((p) => p.status === ENRICHED_STATUS);

  function toggleRow(id: string) {
    setChecked((s) => {
      const n = new Set(s);
      if (n.has(id)) n.delete(id);
      else n.add(id);
      return n;
    });
  }
  function toggleAll(on: boolean) {
    const ids = visible.map((p) => p.id);
    setChecked((s) => {
      const n = new Set(s);
      for (const id of ids) on ? n.add(id) : n.delete(id);
      return n;
    });
  }

  // ---- Stage 1: companies ----
  const coVisible = useMemo(
    () =>
      companies.filter((c) => {
        const text = `${c.name} ${c.domain} ${c.industry}`.toLowerCase();
        const accepted = c.status === "people_found";
        const statusOk =
          !coStatus || (coStatus === "accepted" ? accepted : !accepted);
        return (
          (!coSearch || text.includes(coSearch.toLowerCase())) &&
          (!coFit || c.fit_tier === coFit) &&
          statusOk
        );
      }),
    [companies, coSearch, coFit, coStatus]
  );
  const coSelCount = coVisible.filter((c) => companyChecked.has(c.id)).length;
  // A background AI-scoring pass (Find / Find Lookalike / Update AI Score) is running for ≥1 row.
  const scoringActive = scoringCoIds.size > 0;
  const scoringPeopleActive = scoringPersonIds.size > 0;
  const coAllChecked = coVisible.length > 0 && coSelCount === coVisible.length;
  // Sample company for the Fit-rubric preview: the first ticked row, else the first one in view. Its
  // id is sent to GET /companies/fit-prompt so the modal shows that row's real input prompt.
  const rubricSample = useMemo(
    () => coVisible.find((c) => companyChecked.has(c.id)) ?? coVisible[0] ?? companies[0] ?? null,
    [coVisible, companyChecked, companies]
  );
  // List is "fetching" during initial hydrate, an Apollo find, or a re-score — show the overlay
  // spinner over the table for the whole period, whether or not rows already exist.
  // Note: `scoringActive` is deliberately NOT here — background scoring keeps the table visible with
  // per-row "Scoring…" status instead of the full-list overlay.
  const coBusy = companiesLoading || findingCo || updatingFields || findingLookalike;
  const pplBusy = prospectsLoading || findingPpl;
  // One-line read of the scope Find Companies will use right now (override or AI spec) — shown in
  // the empty state so a 0-result is explainable, not mysterious.
  const coScopeSummary = useMemo(
    () => scopeSummary(effectiveScope(scopeOverride, spec)),
    [scopeOverride, spec]
  );
  const pplScopeSummary = useMemo(
    () => peopleScopeSummary(effectivePeopleScope(peopleScopeOverride, spec)),
    [peopleScopeOverride, spec]
  );
  function toggleCo(id: string) {
    setCompanyChecked((s) => {
      const n = new Set(s);
      n.has(id) ? n.delete(id) : n.add(id);
      return n;
    });
  }
  function toggleAllCo(on: boolean) {
    const ids = coVisible.map((c) => c.id);
    setCompanyChecked((s) => {
      const n = new Set(s);
      for (const id of ids) on ? n.add(id) : n.delete(id);
      return n;
    });
  }

  async function submitAddCompany() {
    if (!coForm.domain.trim()) return toast("A company domain is required", "warn");
    setSavingCo(true);
    try {
      await addCompany(client, { ...coForm, icp_id: fIcp || null });
      toast(`Added ${coForm.name || coForm.domain}`);
      setAddCoOpen(false);
      setCoForm({ ...blankCo });
      await reloadCompanies();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Add failed", "warn");
    } finally {
      setSavingCo(false);
    }
  }

  // Flow A — Apollo company search from the saved ResearchSpec (or the Settings override). Needs a
  // generated scope. The 0-result toast distinguishes "Apollo matched nothing" (loosen filters)
  // from "matched but all filtered out as dupes/exclusions" (`dropped`) so the cause is explainable.
  async function runFindCompanies() {
    setFindingCo(true);
    try {
      const res = await findCompanies(client, { icp_id: fIcp || null, ...(scopeOverride ?? {}) });
      await reloadCompanies();
      if (res.found) {
        const tail = res.dropped ? ` · ${res.dropped} filtered out` : "";
        // Rows land unscored and stay that way (AI Score shows "Pending"); the operator scores on
        // demand by selecting rows and clicking Update AI Score. No auto-trigger.
        toast(
          `Found ${res.found} ${res.found === 1 ? "company" : "companies"}${tail} · ` +
            "select rows and click Update AI Score to score them"
        );
      } else if (res.dropped) {
        toast(
          `Apollo returned ${res.dropped}, but all were filtered out as duplicates or exclusions. ` +
            "Adjust the scope in ⚙ Settings.",
          "warn"
        );
      } else {
        toast(
          "No companies matched the current scope. Loosen the filters in ⚙ Settings " +
            "(geo, size, keywords, or the funding/hiring windows).",
          "warn"
        );
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Find companies failed", "warn");
    } finally {
      setFindingCo(false);
    }
  }

  // Re-run fit scoring for the checked companies (e.g. after the rubric / scoring prompt changed).
  // Unlike Find, this re-scores rows that already have a score — each call is a paid LLM request.
  // Runs in the BACKGROUND (chunked, per-row "Scoring…" status) so the UI never blocks and a slow
  // LLM call can never time the request out.
  function runRescore() {
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to re-score", "warn");
    toast(`Re-scoring ${ids.length} ${ids.length === 1 ? "company" : "companies"} in the background…`);
    void scoreInBackground(ids);
  }

  // "Update Field" — re-enrich Apollo firmographics for the selected rows. Each call spends Apollo
  // credits, so it is deliberate/manual (Find Companies enriches only new rows).
  async function runUpdateFields() {
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to update", "warn");
    setUpdatingFields(true);
    try {
      await updateCompanyFields(client, ids);
      await reloadCompanies();
      toast(`Updated ${ids.length} ${ids.length === 1 ? "company" : "companies"}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Update failed", "warn");
    } finally {
      setUpdatingFields(false);
    }
  }

  // Score a set of company rows in the BACKGROUND, in small chunks so no single request nears the
  // 30s gateway cap. Each chunk re-scores via the existing /rescore endpoint; as it lands, those
  // rows clear their "Scoring…" status and the table refreshes with the new scores. A failed chunk
  // just clears its status (rows stay unscored — recoverable via the Update AI Score button).
  async function scoreInBackground(ids: string[]) {
    const CHUNK = 3; // ~3 reasoning calls per request keeps wall-clock well under 30s
    setScoringCoIds((prev) => new Set([...prev, ...ids]));
    for (let i = 0; i < ids.length; i += CHUNK) {
      const chunk = ids.slice(i, i + CHUNK);
      try {
        await rescoreCompanies(client, chunk);
      } catch {
        /* leave these rows unscored; the manual Update AI Score button can retry */
      } finally {
        if (clientRef.current === client) {
          setScoringCoIds((prev) => {
            const next = new Set(prev);
            chunk.forEach((id) => next.delete(id));
            return next;
          });
        }
      }
      if (clientRef.current !== client) return; // client switched away — stop
      await reloadCompanies();
    }
  }

  // "Find Lookalike" — find the next batch of peers of the checked rows. The seeds are the search
  // input (no Settings modal); the server aggregates their firmographics and drops every company
  // already in the list (seeds included), so `found` is the genuinely-new peers. Rows land UNSCORED
  // and stay that way (AI Score shows "Pending") — the operator scores on demand via Update AI
  // Score. The toast tells the outcomes apart: new / all-listed / none.
  async function runLookalike() {
    const ids = [...companyChecked];
    if (!ids.length) return toast("Select companies to find lookalikes", "warn");
    setFindingLookalike(true);
    try {
      const res = await findLookalikes(client, { company_ids: ids, icp_id: fIcp || null });
      await reloadCompanies();
      if (res.found) {
        const tail = res.dropped ? ` · ${res.dropped} already in your list` : "";
        toast(
          `Found ${res.found} new lookalike ${res.found === 1 ? "company" : "companies"}${tail} · ` +
            "select rows and click Update AI Score to score them"
        );
      } else if (res.dropped) {
        toast(
          `Apollo returned ${res.dropped} similar ${res.dropped === 1 ? "company" : "companies"}, ` +
            `but ${res.dropped === 1 ? "it is" : "all are"} already in your list — nothing new to add.`,
          "warn"
        );
      } else {
        toast(
          "No companies similar to the selection were found. The seeds may be too sparse — " +
            "enrich them first (industry, size and revenue drive the match) or select more rows.",
          "warn"
        );
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Lookalike search failed", "warn");
    } finally {
      setFindingLookalike(false);
    }
  }

  // ---- Settings (find-company scope) handlers ----
  function openScopeSettings() {
    setScopeForm(scopeToForm(effectiveScope(scopeOverride, spec)));
    setScopeOpen(true);
  }
  function saveScopeSettings() {
    if (!scopeForm) return;
    const ov = formToOverride(scopeForm);
    setScopeOverride(ov);
    saveScopeOverride(client, ov);
    setScopeOpen(false);
    toast("Search filters saved · used on the next Find");
  }
  function resetScopeSettings() {
    setScopeOverride(null);
    saveScopeOverride(client, null);
    setScopeForm(scopeToForm(effectiveScope(null, spec)));
    toast("Reverted to the AI-generated scope");
  }

  // Step 1 → Step 2: stage the ticked companies (discovered → selected) so they appear in the Step-2
  // table as "Pending" rows, then switch to Step 2. No Apollo call yet — people are found there, per
  // company. The ticks carry over (companyChecked is shared) so Find People is one click away.
  async function stageForPeople() {
    const ids = [...companyChecked];
    if (!ids.length) return;
    setStaging(true);
    try {
      await selectCompanies(client, ids, true);
      await reloadCompanies();
      setListStage("people");
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t move companies to Step 2", "warn");
    } finally {
      setStaging(false);
    }
  }

  // Step 2 → Step 1: remove the ticked companies from Step 2 (selected | people_found → discovered),
  // so an Accepted company can be taken back out of the pursuit. The rows leave the Step-2 table and
  // reappear in the Step-1 list; their checks are cleared.
  async function removeFromStep2() {
    const ids = pplCoSel.map((c) => c.id);
    if (!ids.length) return;
    setRemoving(true);
    try {
      await selectCompanies(client, ids, false);
      await reloadCompanies();
      setCompanyChecked((s) => {
        const n = new Set(s);
        ids.forEach((id) => n.delete(id));
        return n;
      });
      toast(`Removed ${ids.length} ${ids.length === 1 ? "company" : "companies"} from Step 2`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Couldn’t remove companies", "warn");
    } finally {
      setRemoving(false);
    }
  }

  // Flow B — find people at the ticked Step-2 companies (free; enrichment is the credit spend). The
  // search is driven by the explicit company ids, so a row can be re-searched after loosening the
  // filters. People land UNSCORED ("Pending") — the operator scores them via Get AI score.
  async function runFindPeople() {
    const ids = pplCoSel.map((c) => c.id);
    if (!ids.length) return toast("Select companies in the list to find people", "warn");
    setFindingPpl(true);
    setFindingPplIds(new Set(ids));
    try {
      const res = await findPeople(client, {
        company_ids: ids,
        icp_id: fIcp || null,
        ...(peopleScopeOverride ?? {}),
      });
      await Promise.all([reloadProspects(), reloadCompanies()]);
      if (res.found) {
        const tail = res.dropped ? ` · ${res.dropped} filtered out` : "";
        toast(
          `Found ${res.found} ${res.found === 1 ? "person" : "people"}${tail} · ` +
            "select them and click Get AI score to score them"
        );
      } else if (res.dropped) {
        toast(
          `Apollo returned ${res.dropped}, but all were filtered out (already imported, no Apollo id, ` +
            "or an avoided title). Widen the titles/seniorities in ⚙ Settings.",
          "warn"
        );
      } else {
        toast(
          "No people matched at the selected companies. Loosen the titles, seniorities, or keywords " +
            "in ⚙ Settings.",
          "warn"
        );
      }
    } catch (e) {
      toast(e instanceof Error ? e.message : "Find people failed", "warn");
    } finally {
      setFindingPpl(false);
      setFindingPplIds(new Set());
    }
  }

  // Step-2 'Get AI score' — re-score the checked people in the background (chunked, per-row
  // "Scoring…"), mirroring the Step-1 company scorer. Each call is a paid LLM request.
  function runScorePeople() {
    const picked = selectedProspects;
    if (!picked.length) return toast("Select people to score", "warn");
    toast(`Scoring ${picked.length} ${picked.length === 1 ? "person" : "people"} in the background…`);
    void scorePeopleInBackground(picked.map((p) => ({ id: p.id, key: p.identity_key })));
  }

  async function scorePeopleInBackground(rows: { id: string; key: string }[]) {
    const CHUNK = 3; // a few reasoning calls per request keeps wall-clock well under the 30s cap
    setScoringPersonIds((prev) => new Set([...prev, ...rows.map((r) => r.id)]));
    for (let i = 0; i < rows.length; i += CHUNK) {
      const chunk = rows.slice(i, i + CHUNK);
      try {
        await rescoreProspects(client, chunk.map((r) => r.key));
      } catch {
        /* leave these rows unscored; the manual Get AI score button can retry */
      } finally {
        if (clientRef.current === client) {
          setScoringPersonIds((prev) => {
            const next = new Set(prev);
            chunk.forEach((r) => next.delete(r.id));
            return next;
          });
        }
      }
      if (clientRef.current !== client) return; // client switched away — stop
      await reloadProspects();
    }
  }

  // ---- Step-2 Settings (find-people scope) handlers ----
  function openPeopleScopeSettings() {
    setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(peopleScopeOverride, spec)));
    setPeopleScopeOpen(true);
  }
  function savePeopleScopeSettings() {
    if (!peopleScopeForm) return;
    const ov = formToPeopleOverride(peopleScopeForm);
    setPeopleScopeOverride(ov);
    savePeopleScopeOverride(client, ov);
    setPeopleScopeOpen(false);
    toast("Person filters saved · used on the next Find People");
  }
  function resetPeopleScopeSettings() {
    setPeopleScopeOverride(null);
    savePeopleScopeOverride(client, null);
    setPeopleScopeForm(peopleScopeToForm(effectivePeopleScope(null, spec)));
    toast("Reverted to the AI-generated person scope");
  }

  // ---- Stage 2: people ----
  async function submitAddPerson() {
    if (
      !personForm.full_name.trim() &&
      !personForm.email.trim() &&
      !personForm.linkedin_url.trim()
    ) {
      return toast("Add a name + company domain, a LinkedIn URL, or an email", "warn");
    }
    setSavingPerson(true);
    try {
      await addProspect(client, { ...personForm, icp_id: fIcp || null });
      toast(`Added ${personForm.full_name || personForm.email}`);
      setAddPersonOpen(false);
      setPersonForm({ ...blankPerson });
      await Promise.all([reloadProspects(), reloadCompanies()]);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Add failed", "warn");
    } finally {
      setSavingPerson(false);
    }
  }

  // The enrich gate — confirm the selected scored people for enrichment. (The paid Apollo
  // people/match enrichment is wired server-side in Phase C; this flips status for now.)
  async function confirmEnrich() {
    if (enriching) return;
    const keys = toEnrich.map((p) => p.identity_key);
    if (!keys.length) return toast("Select found people to confirm for enrichment", "warn");
    setEnriching(true);
    try {
      const res = await enrichProspects(client, keys);
      toast(
        res.enriched
          ? `Enriched ${res.enriched} · ${res.credits_spent} credit${res.credits_spent === 1 ? "" : "s"} spent`
          : `Confirmed ${res.confirmed}`
      );
      await reloadProspects();
    } catch (e) {
      toast(e instanceof Error ? e.message : "Confirm failed", "warn");
    } finally {
      setEnriching(false);
    }
  }

  // Open the Fit-rubric modal and fetch the real fit-score prompt for one sample company (the first
  // ticked row, else the first in view) — the backend builds it from this client's brief + research
  // spec + ICP docs, so the Input-prompt pane shows exactly what reaches the model.
  async function openRubric() {
    setShowSourcing(true);
    setFitPrompt(null);
    setFitPromptErr(null);
    setFitPromptLoading(true);
    try {
      const fp = await getFitPrompt(client, rubricSample?.id);
      setFitPrompt(fp);
    } catch (e) {
      setFitPromptErr(e instanceof Error ? e.message : "Could not load the input prompt");
    } finally {
      setFitPromptLoading(false);
    }
  }

  // Save the founder's edit as the next version of the fit rubric (append-only vN+1).
  async function saveDoc(stage: "fit_scoring") {
    const body = rubricDraft.trim();
    if (!body) return toast("Nothing to save", "warn");
    setSavingDoc(stage);
    try {
      await saveSourcingDoc(client, stage, body);
      const dl = await getSourcingDocs(client);
      setDocs(dl);
      toast(`Saved fit rubric v${dl.fit_scoring?.version}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "Save failed", "warn");
    } finally {
      setSavingDoc(null);
    }
  }

  function createBatch() {
    const name = newBatchName.trim() || "Batch " + (batches.length + 1);
    // Only enriched people can be batched — enforce enrich-before-batch (the dock already gates
    // the button; re-check here so a stale click can't slip unenriched rows through).
    const picked = enrichedSel;
    if (!picked.length) {
      return toast("Select enriched people — enrich the Found ones first", "warn");
    }
    const icpSet = new Set(picked.map((p) => (p.icp_id ? icpNameById.get(p.icp_id) : null) || "—"));
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
    setChecked(new Set());
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
      "Amount (USD)",
    ];
    const rows = LEDGER.map((row, i) => [
      "Placeholder date",
      "Prospect " + (i + 1),
      "Sample Co " + (i + 1),
      "Campaign 1",
      "Batch 3",
      row.outcome,
      row.feedback,
      row.billing,
      row.billing === "Billed" ? String(PER_MEETING_USD) : "",
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

  // batch approval action: send the approval email, or nudge if it was already sent
  const sendApproval = (name: string) => {
    const alreadySent = !!batches.find((x) => x.name === name)?.sentAt;
    setBatches((s) =>
      s.map((b) => (b.name === name ? { ...b, sentAt: b.sentAt || TODAY_ISO } : b))
    );
    toast(alreadySent ? "Follow-up nudge sent to client" : "Approval email sent to client");
  };

  // Group a batch's prospects under their company — company is the primary row, its related
  // staff listed beneath. Distributes b.count people across companies of 2–3, sorted by company.
  const batchCompanies = (b: Batch) => {
    const groups: {
      company: string;
      domain: string;
      score: (typeof SCORE_TIERS)[number];
      industry: string;
      connectedTo: string;
      people: { name: string; role: string; status: string }[];
    }[] = [];
    let placed = 0;
    let ci = 0;
    while (placed < b.count) {
      const size = Math.min((ci % 2) + 2, b.count - placed); // 2, 3, 2, 3 …
      const people = Array.from({ length: size }, (_, k) => {
        const idx = placed + k;
        return {
          name: "Prospect " + (idx + 1),
          role: STAFF_ROLES[idx % STAFF_ROLES.length],
          status: idx < b.approved ? "Approved" : b.status === "Rejected" ? "Rejected" : "Pending",
        };
      });
      groups.push({
        company: "Sample Co " + (ci + 1),
        domain: "sampleco" + (ci + 1) + ".com",
        score: SCORE_TIERS[ci % SCORE_TIERS.length],
        industry: SAMPLE_INDUSTRIES[ci % SAMPLE_INDUSTRIES.length],
        connectedTo: SAMPLE_CONNECTIONS[ci % SAMPLE_CONNECTIONS.length],
        people,
      });
      placed += size;
      ci++;
    }
    return groups;
  };

  const tabBar = (
    <div className="tabs ws-tabs" role="tablist">
      {TABS.map(([k, label]) => (
        <button key={k} className={clsx("tab", tab === k && "active")} onClick={() => activate(k)}>
          {label}
          {k === "batches" && <span className="cnt">{batches.length}</span>}
          {k === "campaign" && <span className="cnt">{campaigns.length}</span>}
          {k === "replies" && (
            <span className={clsx("cnt", remaining > 0 && "alert")}>{remaining}</span>
          )}
        </button>
      ))}
    </div>
  );

  return (
    <>
      {tabSlot ? createPortal(tabBar, tabSlot) : tabBar}

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
                        onChange={(e) => onCsv("customers", e)}
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
                        onChange={setNoExclude(
                          "noExcludeCustomers",
                          "excludeCustomers",
                          "customers"
                        )}
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
                        onChange={(e) => onCsv("deals", e)}
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
                        onChange={(e) => onCsv("doNotContact", e)}
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
              client={client}
              spec={spec}
              structuring={structuring}
              saving={saving}
              ready={allComplete}
              onStructure={runStructure}
              onAcceptIcp={acceptIcpSuggestion}
            />
          </>
        )}
      </section>

      {/* PROSPECT LIST */}
      <section className={clsx("tabpane list-pane", tab === "list" && "active")}>
        <div className="panel">
          <div className="panel-head">
            <div className="tabs">
              <button
                className={clsx("tab", listStage === "companies" && "active")}
                onClick={() => setListStage("companies")}
              >
                <span className="tab-num">Step 1</span> Companies{" "}
                <span className="tab-ct">({companies.length})</span>
              </button>
              <span className="tab-chev" aria-hidden="true">
                →
              </span>
              <button
                className={clsx("tab", listStage === "people" && "active")}
                onClick={() => setListStage("people")}
              >
                <span className="tab-num">Step 2</span> People{" "}
                <span className="tab-ct">({prospects.length})</span>
              </button>
            </div>
            <div className="head-actions">
              <button className="btn btn-ghost btn-sm" onClick={openRubric}>
                Fit Rubric
              </button>
              {listStage === "companies" ? (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={runRescore}
                  disabled={!coSelCount || scoringActive || findingPpl}
                  title="Re-run fit scoring for the selected companies · one paid LLM call each"
                >
                  {scoringActive
                    ? "Scoring…"
                    : coSelCount
                      ? `Get AI score ${coSelCount}`
                      : "Get AI score"}
                </button>
              ) : (
                <button
                  className="btn btn-ghost btn-sm"
                  onClick={runScorePeople}
                  disabled={!selCount || scoringPeopleActive || findingPpl}
                  title="Run fit scoring for the selected people · one paid LLM call each"
                >
                  {scoringPeopleActive
                    ? "Scoring…"
                    : selCount
                      ? `Get AI score ${selCount}`
                      : "Get AI score"}
                </button>
              )}
            </div>
          </div>

          {listStage === "companies" ? (
            <>
              <div className="list-band">
                <h3>Find companies likely to buy</h3>
                <div className="band-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={openScopeSettings}
                    title="Edit the Apollo company-search filters used by Find Company"
                  >
                    Find Settings
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={runFindCompanies}
                    disabled={findingCo}
                    title="Search Apollo from the current scope · enriches only new companies"
                  >
                    {findingCo ? "Finding…" : "Find Company"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={runLookalike}
                    disabled={!coSelCount || findingLookalike || findingCo}
                    title="Find the next batch of companies similar to the selected rows · spends Apollo credits"
                  >
                    {findingLookalike
                      ? "Finding…"
                      : coSelCount
                        ? `Find Lookalike ${coSelCount}`
                        : "Find Lookalike"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={runUpdateFields}
                    disabled={!coSelCount || updatingFields || findingCo}
                    title="Re-enrich Apollo firmographics for the selected companies · spends Apollo credits"
                  >
                    {updatingFields
                      ? "Updating…"
                      : coSelCount
                        ? `Enrichment ${coSelCount}`
                        : "Enrichment"}
                  </button>
                </div>
              </div>
              <div className="filter-row list-toolbar">
                <div className="search">
                  <span className="si">⌕</span>
                  <input
                    className="input"
                    type="text"
                    placeholder="Search company or domain"
                    value={coSearch}
                    onChange={(e) => setCoSearch(e.target.value)}
                  />
                </div>
                <select
                  className="select"
                  value={coStatus}
                  onChange={(e) => setCoStatus(e.target.value)}
                >
                  <option value="">All status</option>
                  <option value="accepted">Accepted</option>
                  <option value="pending">Pending</option>
                </select>
                <select className="select" value={coFit} onChange={(e) => setCoFit(e.target.value)}>
                  <option value="">Any fit</option>
                  <option value="Strong">Strong fit</option>
                  <option value="Good">Good fit</option>
                  <option value="Moderate">Moderate fit</option>
                  <option value="Below">Below</option>
                </select>
                <button className="btn btn-ghost btn-sm" onClick={() => setAddCoOpen(true)}>
                  Manual Upload
                </button>
              </div>
              <div className="countrow">
                <b>{coVisible.length}</b>&nbsp;shown&nbsp;·&nbsp;<b>{coSelCount}</b>&nbsp;selected
              </div>
              <div className="list-body">
                {coBusy && (
                  <div className="list-overlay" role="status" aria-live="polite">
                    <span className="hs-spinner" aria-hidden="true" />
                    <span>Fetching…</span>
                  </div>
                )}
                <div className="list-scroll">
                <table className="tbl">
                  <thead>
                    <tr>
                      <th style={{ width: 34 }}>
                        <input
                          type="checkbox"
                          className="tbl-check"
                          checked={coAllChecked}
                          onChange={(e) => toggleAllCo(e.target.checked)}
                        />
                      </th>
                      <th>Company</th>
                      <th>AI Score</th>
                      <th>Domain</th>
                      <th>Website</th>
                      <th>Industry</th>
                      <th>Size</th>
                      <th>Source</th>
                      <th>Enrichment</th>
                    </tr>
                  </thead>
                  {coVisible.length > 0 && (
                    <tbody>
                      {coVisible.map((c) => (
                        <tr key={c.id} className={clsx(companyChecked.has(c.id) && "row-sel")}>
                          <td>
                            <input
                              type="checkbox"
                              className="tbl-check"
                              checked={companyChecked.has(c.id)}
                              onChange={() => toggleCo(c.id)}
                            />
                          </td>
                          <td>
                            <div className="who-cell">
                              <div>
                                {c.status === "people_found" ? (
                                  <span className="sel-tag">Accepted</span>
                                ) : null}
                                <div className="nm">{c.name || c.domain}</div>
                                {c.country ? <div className="sub">{c.country}</div> : null}
                              </div>
                            </div>
                          </td>
                          <td>
                            {scoringCoIds.has(c.id) ? (
                              <span className="fit-scoring" title="AI fit-scoring in progress">
                                <span className="hs-spinner" aria-hidden="true" />
                                Scoring…
                              </span>
                            ) : (
                              <FitScore
                                tier={c.fit_tier}
                                score={c.fit_score}
                                reason={c.fit_reason}
                              />
                            )}
                          </td>
                          <td>
                            <span className="domain">{c.domain}</span>
                          </td>
                          <td>
                            <WebLink website={c.website} domain={c.domain} />
                          </td>
                          <td className="muted">{c.industry || "—"}</td>
                          <td className="muted">{c.size || "—"}</td>
                          <td>
                            <span
                              className={clsx("badge", SOURCE_CLS[c.source] ?? "badge-neutral")}
                            >
                              <span className="bdot" />
                              {SOURCE_LABEL[c.source] ?? c.source}
                            </span>
                          </td>
                          <td>
                            <CompanyStudy e={c.enrichment} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  )}
                </table>
                {coVisible.length === 0 && (
                  <div className="list-empty muted">
                    No companies match the current scope yet · click Find Companies to search Apollo.
                    <br />
                    {coScopeSummary ? (
                      <>
                        Active filters{scopeOverride ? " (custom)" : ""} · {coScopeSummary}.
                        <br />
                        Too few results? Widen them in ⚙ Settings, or + Add company manually.
                      </>
                    ) : (
                      <>Set your filters in ⚙ Settings, or + Add company manually. Finding is free.</>
                    )}
                  </div>
                )}
                </div>
              </div>
              <div className="list-dock">
                <span className={clsx("dock-count", !coSelCount && "empty")}>
                  {coSelCount ? (
                    <>
                      <b>{coSelCount}</b> companies selected
                    </>
                  ) : (
                    "Select companies to move to Step 2"
                  )}
                </span>
                {coSelCount ? (
                  <button className="dock-clear" onClick={() => setCompanyChecked(new Set())}>
                    Clear
                  </button>
                ) : null}
                <span className="dock-spacer" />
                <button
                  className="btn btn-primary"
                  onClick={() => void stageForPeople()}
                  disabled={!coSelCount || staging}
                >
                  {staging ? "Moving…" : `Find people for ${coSelCount} →`}
                </button>
              </div>
            </>
          ) : (
            <>
              <div className="list-band">
                <h3>Find the right person</h3>
                <div className="band-actions">
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={openPeopleScopeSettings}
                    title="Edit the Apollo people-search filters used by Find People"
                  >
                    Find Settings
                  </button>
                  <button
                    className="btn btn-primary btn-sm"
                    onClick={runFindPeople}
                    disabled={findingPpl || !pplCoSel.length}
                    title="Find people at the ticked companies (free; enrich spends credits)"
                  >
                    {findingPpl
                      ? "Finding…"
                      : pplCoSel.length
                        ? `Find People ${pplCoSel.length}`
                        : "Find People"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={confirmEnrich}
                    disabled={!canEnrich || enriching}
                    title={
                      canEnrich
                        ? "Enrich the selected Found people · spends Apollo credits"
                        : "Select people marked Found to enrich them."
                    }
                  >
                    {enriching
                      ? "Confirming…"
                      : toEnrich.length
                        ? `Confirm enrich ${toEnrich.length}`
                        : "Confirm enrich"}
                  </button>
                  <button
                    className="btn btn-ghost btn-sm"
                    onClick={() => void removeFromStep2()}
                    disabled={!pplCoSel.length || removing}
                    title="Remove the ticked companies from Step 2 (back to the Step-1 list)"
                  >
                    {removing
                      ? "Removing…"
                      : pplCoSel.length
                        ? `Remove ${pplCoSel.length}`
                        : "Remove"}
                  </button>
                </div>
              </div>
              <div className="filter-row list-toolbar">
                <div className="search">
                  <span className="si">⌕</span>
                  <input
                    className="input"
                    type="text"
                    placeholder="Search company or domain"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                  />
                </div>
                <select className="select" value={fFit} onChange={(e) => setFFit(e.target.value)}>
                  <option value="">Any fit</option>
                  <option value="Strong">Strong fit</option>
                  <option value="Good">Good fit</option>
                  <option value="Moderate">Moderate fit</option>
                  <option value="Below">Below</option>
                </select>
                <button className="btn btn-ghost btn-sm" onClick={() => setAddPersonOpen(true)}>
                  Manual Upload
                </button>
              </div>
              <div className="countrow">
                <b>{pursued.length}</b>&nbsp;companies&nbsp;·&nbsp;<b>{visible.length}</b>&nbsp;people&nbsp;·&nbsp;
                <b>{selCount}</b>&nbsp;selected
              </div>
              <div className="list-body">
                {pplBusy && (
                  <div className="list-overlay" role="status" aria-live="polite">
                    <span className="hs-spinner" aria-hidden="true" />
                    <span>Fetching…</span>
                  </div>
                )}
                <div className="list-scroll">
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
                      <th>Company</th>
                      <th>Prospect</th>
                      <th>LinkedIn</th>
                      <th>Title</th>
                      <th>AI Score</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  {pursued.length > 0 && (
                    <tbody>
                      {pursued.map((c) => {
                        const rows = rowsForCompany(c.id);
                        const finding = findingPplIds.has(c.id);
                        const searched = c.status === "people_found";
                        return (
                          <Fragment key={c.id}>
                            <tr className="grp-row">
                              <td>
                                <input
                                  type="checkbox"
                                  className="tbl-check"
                                  checked={companyChecked.has(c.id)}
                                  onChange={() => toggleCo(c.id)}
                                  title="Select this company to find people"
                                />
                              </td>
                              <td>
                                <div className="grp-co">
                                  <span className="nm">{c.name || c.domain}</span>
                                  {c.domain ? <span className="domain">{c.domain}</span> : null}
                                </div>
                              </td>
                              <td className="muted grp-hint" colSpan={4}>
                                {finding
                                  ? "Finding people…"
                                  : !searched
                                    ? "Tick this company, then Find People"
                                    : rows.length === 0
                                      ? "No people found · loosen Find Settings, then Find People again"
                                      : null}
                              </td>
                              <td>
                                {finding ? (
                                  <span className="fit-scoring">
                                    <span className="hs-spinner" aria-hidden="true" />
                                    Finding…
                                  </span>
                                ) : !searched ? (
                                  <span className="badge badge-warn">
                                    <span className="bdot" />
                                    Pending
                                  </span>
                                ) : rows.length === 0 ? (
                                  <span className="badge badge-neutral">
                                    <span className="bdot" />0 people
                                  </span>
                                ) : (
                                  <span className="badge badge-info">
                                    <span className="bdot" />
                                    {rows.length} {rows.length === 1 ? "person" : "people"}
                                  </span>
                                )}
                              </td>
                            </tr>
                            {rows.map((p) => {
                              const enriched = p.status === ENRICHED_STATUS;
                              const stClass = enriched
                                ? "st--enriched"
                                : p.status === "score_error" || p.status === "enrich_failed"
                                  ? "st--error"
                                  : "st--found";
                              const stMeta = enriched
                                ? "email verified"
                                : p.status === "confirmed"
                                  ? "awaiting enrichment"
                                  : p.status === "score_error"
                                    ? "scoring failed"
                                    : p.status === "enrich_failed"
                                      ? "no Apollo match"
                                      : "no email yet";
                              return (
                                <tr key={p.id} className={clsx(checked.has(p.id) && "row-sel")}>
                                  <td>
                                    <input
                                      type="checkbox"
                                      className="tbl-check"
                                      checked={checked.has(p.id)}
                                      onChange={() => toggleRow(p.id)}
                                    />
                                  </td>
                                  <td />
                                  <td>
                                    <div className="who-cell">
                                      <div className="av-sm">
                                        {(p.full_name || p.company || "?")
                                          .slice(0, 2)
                                          .toUpperCase()}
                                      </div>
                                      <div>
                                        <div className="nm">{p.full_name || "—"}</div>
                                        <div className="sub">{p.email || "no email yet"}</div>
                                      </div>
                                    </div>
                                  </td>
                                  <td>
                                    <LinkedInLink url={p.linkedin_url} />
                                  </td>
                                  <td className="muted">{p.title || "—"}</td>
                                  <td>
                                    {scoringPersonIds.has(p.id) ? (
                                      <span className="fit-scoring" title="AI fit-scoring in progress">
                                        <span className="hs-spinner" aria-hidden="true" />
                                        Scoring…
                                      </span>
                                    ) : (
                                      <FitScore
                                        tier={p.fit_tier}
                                        score={p.fit_score}
                                        reason={p.fit_reason}
                                      />
                                    )}
                                  </td>
                                  <td>
                                    <div className="st2">
                                      <span className={clsx("st", stClass)}>
                                        <span className="st-dot" />
                                        {STATUS_LABEL[p.status] ?? p.status}
                                      </span>
                                      <span className="st-meta">{stMeta}</span>
                                    </div>
                                  </td>
                                </tr>
                              );
                            })}
                          </Fragment>
                        );
                      })}
                    </tbody>
                  )}
                </table>
                {pursued.length === 0 && (
                  <div className="list-empty muted">
                    {prospectsLoading || companiesLoading ? (
                      "Loading…"
                    ) : (
                      <>
                        No companies in Step 2 yet · go to Step 1, tick companies, and click
                        “Find people for N →”.
                        {pplScopeSummary ? (
                          <>
                            <br />
                            Person filters{peopleScopeOverride ? " (custom)" : ""} · {pplScopeSummary}
                            . Adjust them in ⚙ Settings.
                          </>
                        ) : null}
                      </>
                    )}
                  </div>
                )}
                </div>
              </div>
              <div className="list-dock">
                <span className={clsx("dock-count", !selectedProspects.length && "empty")}>
                  {selectedProspects.length ? (
                    <>
                      <b>{selectedProspects.length}</b> selected
                      {toEnrich.length && enrichedSel.length ? (
                        <span className="sub"> · {toEnrich.length} need enrichment first</span>
                      ) : null}
                    </>
                  ) : (
                    "Select people to create batch"
                  )}
                </span>
                {selectedProspects.length ? (
                  <button className="dock-clear" onClick={() => setChecked(new Set())}>
                    Clear
                  </button>
                ) : null}
                <span className="dock-spacer" />
                <div className={clsx("dock-act", canBatch ? "on" : "off")}>
                  <input
                    className="input dock-name"
                    type="text"
                    placeholder="Name this batch"
                    value={newBatchName}
                    onChange={(e) => setNewBatchName(e.target.value)}
                    disabled={!canBatch}
                  />
                  <button
                    className="btn btn-primary"
                    onClick={createBatch}
                    disabled={!canBatch}
                    title={
                      canBatch
                        ? ""
                        : toEnrich.length
                          ? "Enrich the Found people first — only enriched people can be batched."
                          : "Select enriched people to batch them."
                    }
                  >
                    Create batch →
                  </button>
                </div>
              </div>
            </>
          )}
        </div>

        {/* FIT RUBRIC MODAL — the versioned scoring rubric (append-only) */}
        <Modal
          open={showSourcing}
          onClose={() => setShowSourcing(false)}
          title={`Fit rubric · ${clientName}`}
          subtitle="The exact system + input prompt sent to the model to score each company."
          className="modal-lg"
          footer={
            <button className="btn btn-primary btn-sm" onClick={() => setShowSourcing(false)}>
              Done
            </button>
          }
        >
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
            {fitPrompt && (
              <span className="badge badge-info">model · {fitPrompt.model.join(" → ")}</span>
            )}
            <span className="badge badge-neutral">
              purpose · {fitPrompt?.purpose ?? "company_fit"}
            </span>
            <span className="badge badge-neutral">rubric v{docs?.fit_scoring?.version ?? "—"}</span>
          </div>
          <div className="prompt-cols">
            {/* LEFT — System prompt: the rubric, editable + saved as the next version. */}
            <div className="prompt-col">
              <div className="prompt-col-head">
                <label>
                  System prompt{" "}
                  <span className="badge badge-neutral">v{docs?.fit_scoring?.version ?? "—"}</span>
                </label>
                <div className="row" style={{ gap: 8, alignItems: "center" }}>
                  <button
                    type="button"
                    className="btn btn-accent btn-xs"
                    onClick={() => saveDoc("fit_scoring")}
                    disabled={savingDoc === "fit_scoring"}
                  >
                    {savingDoc === "fit_scoring" ? "Saving…" : "Save as new version"}
                  </button>
                </div>
              </div>
              <textarea
                className="prompt-edit"
                value={rubricDraft}
                spellCheck={false}
                onChange={(e) => setRubricDraft(e.target.value)}
              />
            </div>
            {/* RIGHT — Input prompt: the REAL message the model receives, fetched from the API
                (targeting context = this client's brief + research spec + ICP docs + sample co). */}
            <div className="prompt-col">
              <div className="prompt-col-head">
                <label>Input prompt</label>
                <span className="ph-sub">
                  {fitPromptLoading
                    ? "loading…"
                    : fitPrompt?.company
                      ? `read-only · sample: ${fitPrompt.company}`
                      : "read-only · no company yet"}
                </span>
              </div>
              <pre className="prompt-pre">
                {fitPromptLoading
                  ? "Loading the input prompt…"
                  : fitPromptErr
                    ? fitPromptErr
                    : fitPrompt?.user || "Find a company first to preview its input prompt."}
              </pre>
            </div>
          </div>
          <div className="ph-sub prompt-hint">
            Edits are saved for this client and used on the next re-score. Each company is scored
            against this rubric with the input prompt shown on the right.
          </div>
        </Modal>

        {/* FIND-COMPANY SCOPE SETTINGS — edit the Apollo company-search filters Phase B produced.
            Empty fields are dropped server-side (they simply widen the search). */}
        <Modal
          open={scopeOpen}
          className="modal-lg"
          onClose={() => setScopeOpen(false)}
          title="Find Companies · search filters"
          subtitle="Apollo company-search filters, pre-filled from your AI scope · blank fields are dropped · saved per client for the next Find."
          footer={
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={resetScopeSettings}
                title="Discard manual edits and use the AI-generated scope"
              >
                Reset to AI scope
              </button>
              <span style={{ flex: 1 }} />
              <button className="btn btn-ghost btn-sm" onClick={() => setScopeOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary btn-sm" onClick={saveScopeSettings}>
                Save filters
              </button>
            </>
          }
        >
          {scopeForm && (
            <>
              <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
                <span className="badge badge-neutral">search · apollo</span>
                <span className="badge badge-info">pre-filled from AI scope</span>
              </div>
              <SpecHead>Company search · firmographics</SpecHead>
              <div className="sourcing-cols">
                <div className="field">
                  <label>Keywords · industry / market tags (comma-separated)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="Insurtech, Insurance"
                    value={scopeForm.keywords}
                    onChange={(e) => setScopeForm({ ...scopeForm, keywords: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Locations · HQ country / region (comma-separated)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="hong kong, singapore, thailand"
                    value={scopeForm.locations}
                    onChange={(e) => setScopeForm({ ...scopeForm, locations: e.target.value })}
                  />
                </div>
              </div>
              <div className="sourcing-cols" style={{ gridTemplateColumns: "1fr 1fr 1fr" }}>
                <div className="field">
                  <label>Employee size ranges · min,max (; for more)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="10,100 ; 101,500"
                    value={scopeForm.sizes}
                    onChange={(e) => setScopeForm({ ...scopeForm, sizes: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Revenue min (USD)</label>
                  <input
                    className="input"
                    type="number"
                    placeholder="(any)"
                    value={scopeForm.revenueMin}
                    onChange={(e) => setScopeForm({ ...scopeForm, revenueMin: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Revenue max (USD)</label>
                  <input
                    className="input"
                    type="number"
                    placeholder="(any)"
                    value={scopeForm.revenueMax}
                    onChange={(e) => setScopeForm({ ...scopeForm, revenueMax: e.target.value })}
                  />
                </div>
              </div>
              <SpecHead>Buying signals (intent) · optional, narrows hard</SpecHead>
              <div className="field">
                <label>Hiring for job titles (comma-separated)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="sales, growth, commercial"
                  value={scopeForm.hiringTitles}
                  onChange={(e) => setScopeForm({ ...scopeForm, hiringTitles: e.target.value })}
                />
              </div>
              <div className="sourcing-cols" style={{ gridTemplateColumns: "1fr 1fr 1fr 1fr" }}>
                <div className="field">
                  <label>Funded since</label>
                  <input
                    className="input"
                    type="date"
                    value={scopeForm.fundedMin}
                    onChange={(e) => setScopeForm({ ...scopeForm, fundedMin: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Funded until</label>
                  <input
                    className="input"
                    type="date"
                    value={scopeForm.fundedMax}
                    onChange={(e) => setScopeForm({ ...scopeForm, fundedMax: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Jobs posted since</label>
                  <input
                    className="input"
                    type="date"
                    value={scopeForm.jobsMin}
                    onChange={(e) => setScopeForm({ ...scopeForm, jobsMin: e.target.value })}
                  />
                </div>
                <div className="field">
                  <label>Jobs posted until</label>
                  <input
                    className="input"
                    type="date"
                    value={scopeForm.jobsMax}
                    onChange={(e) => setScopeForm({ ...scopeForm, jobsMax: e.target.value })}
                  />
                </div>
              </div>
            </>
          )}
        </Modal>

        {/* FIND-PEOPLE SCOPE SETTINGS — edit the Apollo people-search filters Phase B produced.
            Empty fields are dropped server-side; the org scope comes from your Step-1 selection. */}
        <Modal
          open={peopleScopeOpen}
          className="modal-lg"
          onClose={() => setPeopleScopeOpen(false)}
          title="Find People · search filters"
          subtitle="Apollo people-search filters, pre-filled from your AI scope · only your selected Step-1 companies · blank fields are dropped · saved per client."
          footer={
            <>
              <button
                className="btn btn-ghost btn-sm"
                onClick={resetPeopleScopeSettings}
                title="Discard manual edits and use the AI-generated person scope"
              >
                Reset to AI scope
              </button>
              <span style={{ flex: 1 }} />
              <button className="btn btn-ghost btn-sm" onClick={() => setPeopleScopeOpen(false)}>
                Cancel
              </button>
              <button className="btn btn-primary btn-sm" onClick={savePeopleScopeSettings}>
                Save filters
              </button>
            </>
          }
        >
          {peopleScopeForm && (
            <>
              <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
                <span className="badge badge-neutral">search · apollo</span>
                <span className="badge badge-info">pre-filled from AI scope</span>
              </div>
              <SpecHead>People search · personas</SpecHead>
              <div className="sourcing-cols">
                <div className="field">
                  <label>Job titles to target (comma-separated)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="Head of Sales, VP Sales, Revenue Operations"
                    value={peopleScopeForm.titles}
                    onChange={(e) =>
                      setPeopleScopeForm({ ...peopleScopeForm, titles: e.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label>Seniorities (comma-separated)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="owner, founder, c_suite, vp, director, head, manager"
                    value={peopleScopeForm.seniorities}
                    onChange={(e) =>
                      setPeopleScopeForm({ ...peopleScopeForm, seniorities: e.target.value })
                    }
                  />
                </div>
              </div>
              <label
                className="row"
                style={{ display: "flex", alignItems: "center", gap: 8, margin: "12px 0" }}
              >
                <input
                  type="checkbox"
                  checked={peopleScopeForm.similar}
                  onChange={(e) =>
                    setPeopleScopeForm({ ...peopleScopeForm, similar: e.target.checked })
                  }
                />
                <span>Include similar titles (Apollo expands beyond exact matches)</span>
              </label>
              <div className="field">
                <label>Keywords (free text · name, skill, or focus)</label>
                <input
                  className="input"
                  type="text"
                  placeholder="enterprise sales"
                  value={peopleScopeForm.keywords}
                  onChange={(e) =>
                    setPeopleScopeForm({ ...peopleScopeForm, keywords: e.target.value })
                  }
                />
              </div>
              <SpecHead>Org filters · optional (people are already scoped to your selection)</SpecHead>
              <div className="sourcing-cols">
                <div className="field">
                  <label>Org locations (comma-separated)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="hong kong, singapore"
                    value={peopleScopeForm.locations}
                    onChange={(e) =>
                      setPeopleScopeForm({ ...peopleScopeForm, locations: e.target.value })
                    }
                  />
                </div>
                <div className="field">
                  <label>Org employee size ranges · min,max (; for more)</label>
                  <input
                    className="input"
                    type="text"
                    placeholder="10,100 ; 101,500"
                    value={peopleScopeForm.sizes}
                    onChange={(e) =>
                      setPeopleScopeForm({ ...peopleScopeForm, sizes: e.target.value })
                    }
                  />
                </div>
              </div>
            </>
          )}
        </Modal>

        {/* ADD COMPANY (manual, stage 1) — same schema as an imported row, source=manual */}
        <Modal
          open={addCoOpen}
          onClose={() => setAddCoOpen(false)}
          title="Add company"
          subtitle="Add one company by hand · suppression-checked, then fit-scored against your rubric on save."
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddCoOpen(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={submitAddCompany}
                disabled={savingCo || !coForm.domain.trim()}
              >
                {savingCo ? "Scoring…" : "Add + score"}
              </button>
            </>
          }
        >
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            <span className="badge badge-neutral">source · manual</span>
            <span className="badge badge-info">fit-scored on add</span>
          </div>
          <div className="field">
            <label>Company domain *</label>
            <input
              className="input"
              type="text"
              placeholder="acme.com"
              value={coForm.domain}
              onChange={(e) => setCoForm({ ...coForm, domain: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Name</label>
            <input
              className="input"
              type="text"
              placeholder="Acme Robotics"
              value={coForm.name}
              onChange={(e) => setCoForm({ ...coForm, name: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Website</label>
            <input
              className="input"
              type="text"
              placeholder="https://acme.com"
              value={coForm.website}
              onChange={(e) => setCoForm({ ...coForm, website: e.target.value })}
            />
          </div>
          <div className="sourcing-cols">
            <div className="field">
              <label>Industry</label>
              <input
                className="input"
                type="text"
                value={coForm.industry}
                onChange={(e) => setCoForm({ ...coForm, industry: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Size</label>
              <input
                className="input"
                type="text"
                placeholder="201-500"
                value={coForm.size}
                onChange={(e) => setCoForm({ ...coForm, size: e.target.value })}
              />
            </div>
          </div>
          <div className="sourcing-cols">
            <div className="field">
              <label>Country</label>
              <input
                className="input"
                type="text"
                value={coForm.country}
                onChange={(e) => setCoForm({ ...coForm, country: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Company LinkedIn</label>
              <input
                className="input"
                type="text"
                placeholder="linkedin.com/company/…"
                value={coForm.linkedin_url}
                onChange={(e) => setCoForm({ ...coForm, linkedin_url: e.target.value })}
              />
            </div>
          </div>
          <div className="ph-sub" style={{ marginTop: 16 }}>
            Domain required · rest optional · scored on save.
          </div>
        </Modal>

        {/* ADD PERSON (manual, stage 2) — same schema as an imported row, source=manual */}
        <Modal
          open={addPersonOpen}
          onClose={() => setAddPersonOpen(false)}
          title="Add person"
          subtitle="Add one person by hand · suppression-checked, then fit-scored against your rubric on save."
          footer={
            <>
              <button className="btn btn-ghost btn-sm" onClick={() => setAddPersonOpen(false)}>
                Cancel
              </button>
              <button
                className="btn btn-primary btn-sm"
                onClick={submitAddPerson}
                disabled={savingPerson}
              >
                {savingPerson ? "Scoring…" : "Add + score"}
              </button>
            </>
          }
        >
          <div className="row" style={{ gap: 6, flexWrap: "wrap", marginBottom: 14 }}>
            <span className="badge badge-neutral">source · manual</span>
            <span className="badge badge-info">fit-scored on add</span>
          </div>
          <div className="sourcing-cols">
            <div className="field">
              <label>Full name</label>
              <input
                className="input"
                type="text"
                value={personForm.full_name}
                onChange={(e) => setPersonForm({ ...personForm, full_name: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Title</label>
              <input
                className="input"
                type="text"
                placeholder="VP Engineering"
                value={personForm.title}
                onChange={(e) => setPersonForm({ ...personForm, title: e.target.value })}
              />
            </div>
          </div>
          <div className="sourcing-cols">
            <div className="field">
              <label>Company</label>
              <input
                className="input"
                type="text"
                value={personForm.company}
                onChange={(e) => setPersonForm({ ...personForm, company: e.target.value })}
              />
            </div>
            <div className="field">
              <label>Company domain</label>
              <input
                className="input"
                type="text"
                placeholder="acme.com"
                value={personForm.domain}
                onChange={(e) => setPersonForm({ ...personForm, domain: e.target.value })}
              />
            </div>
          </div>
          <div className="field">
            <label>LinkedIn URL</label>
            <input
              className="input"
              type="text"
              placeholder="linkedin.com/in/…"
              value={personForm.linkedin_url}
              onChange={(e) => setPersonForm({ ...personForm, linkedin_url: e.target.value })}
            />
          </div>
          <div className="field">
            <label>Email (optional — leave blank to enrich later)</label>
            <input
              className="input"
              type="text"
              value={personForm.email}
              onChange={(e) => setPersonForm({ ...personForm, email: e.target.value })}
            />
          </div>
          <div className="ph-sub" style={{ marginTop: 16 }}>
            LinkedIn URL, name + company domain, or email · rest optional · scored on save.
          </div>
        </Modal>

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
                        <th>Company domain</th>
                        <th>Company name</th>
                        <th>Website</th>
                        <th>Type</th>
                      </tr>
                    </thead>
                    <tbody>
                      {EXCLUSIONS.flatMap((g) =>
                        g.entries.map((e) => (
                          <tr key={g.label + e.domain}>
                            <td>
                              <span className="nm">{e.domain}</span>
                            </td>
                            <td className="muted">{e.name}</td>
                            <td className="muted">{e.website}</td>
                            <td>
                              <span className={clsx("badge", g.cls)}>
                                <span className="bdot" />
                                {g.tag}
                              </span>
                            </td>
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
                    <div className="sob-name">{b.name}</div>
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
                            <th>Company</th>
                            <th>Score</th>
                            <th>Industries</th>
                            <th>Connected to</th>
                            <th>Prospect</th>
                            <th>Approval</th>
                          </tr>
                        </thead>
                        <tbody>
                          {batchCompanies(b).map((co) => (
                            <Fragment key={co.company}>
                              {co.people.map((p, pj) => (
                                <tr key={co.company + p.name}>
                                  {/* Company-level cells span the company's staff rows (first row only) */}
                                  {pj === 0 && (
                                    <>
                                      <td className="vtop" rowSpan={co.people.length}>
                                        <span className="nm">{co.company}</span>
                                        <div className="sub">{co.domain}</div>
                                      </td>
                                      <td className="vtop" rowSpan={co.people.length}>
                                        <span className={clsx("badge", co.score.cls)}>
                                          <span className="bdot" />
                                          {co.score.grade} · {co.score.heat}
                                        </span>
                                      </td>
                                      <td className="vtop" rowSpan={co.people.length}>
                                        <span className="icp-chip">{co.industry}</span>
                                      </td>
                                      <td className="vtop muted" rowSpan={co.people.length}>
                                        {co.connectedTo}
                                      </td>
                                    </>
                                  )}
                                  <td>
                                    <span className="nm">{p.name}</span>
                                    <div className="sub">{p.role}</div>
                                  </td>
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
                            </Fragment>
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
                    <div className="nm">{r.n}</div>
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
            <div className="ln">${PER_MEETING_USD}</div>
          </div>
        </div>
        <div className="panel">
          <div className="panel-head">
            <div>
              <h3>Billing Ledger</h3>
              <div className="ph-sub">Only completed, qualified meetings are billable</div>
            </div>
            <button className="btn btn-ghost btn-sm" onClick={exportLedgerCsv}>
              Export CSV
            </button>
          </div>
          <div className="tbl-scroll">
            <table className="tbl">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Meeting with</th>
                  <th>Campaign / Batch</th>
                  <th>Outcome</th>
                  <th>Feedback</th>
                  <th>Status</th>
                  <th className="amt-cell">Amount</th>
                </tr>
              </thead>
              <tbody>
                {LEDGER.map((row, i) => (
                  <tr key={i}>
                    <td className="muted">Placeholder date</td>
                    <td>
                      <div className="nm">Prospect {i + 1}</div>
                      <div className="sub">Sample Co {i + 1}</div>
                    </td>
                    <td>
                      <div className="sum-tags">
                        <span className="stag">Campaign 1</span>
                        <span className="stag">Batch 3</span>
                      </div>
                    </td>
                    <td>
                      <span className={clsx("badge", row.outcomeBadge)}>
                        <span className="bdot" />
                        {row.outcome}
                      </span>
                    </td>
                    <td className="muted">{row.feedback}</td>
                    <td>
                      <span className={clsx("badge", row.billingBadge)}>
                        <span className="bdot" />
                        {row.billing}
                      </span>
                    </td>
                    <td className="amt-cell">
                      {row.billing === "Billed" ? (
                        `$${PER_MEETING_USD}`
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
                      Meeting {sx + 1} · Prospect {sx + 1}
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

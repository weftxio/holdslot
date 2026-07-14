import {
  type BatchApi,
  type BriefDoc,
  type IcpApi,
  type ProspectApi,
  type ScoreLabel,
  type ResearchSpecResult,
} from "@/lib/api";
import { type ExclRow, parseExclusionCsv } from "@/lib/csv";
import { parseUtc } from "@/lib/dates";
import type {
  Batch,
  Brief,
  Icp,
  IcpFields,
  PeopleScopeForm,
  PeopleScopeOverride,
  Range,
  ScopeForm,
  ScopeOverride,
  ScoringSetter,
} from "./types";

export const TABS = [
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
export const STATUS_LABEL: Record<string, string> = {
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
// Origin chip (not transport): where the row came from. New rows are apollo | manual; any other
// value falls back to a neutral chip showing the raw source.
export const SOURCE_CLS: Record<string, string> = {
  apollo: "badge-info",
  manual: "badge-warn",
};
export const SOURCE_LABEL: Record<string, string> = {
  apollo: "Apollo",
  manual: "Manual",
};
// Enriched-and-ready-to-batch. (The old NEEDS_ENRICH status set was dropped in D+.5/R14 — the spend
// estimate now keys on `!email`, not status, so `enrich_failed` no-email rows count as re-spend.)
export const ENRICHED_STATUS = "scored";
export const BATCH_STATUS_CLS: Record<string, string> = {
  Approved: "badge-ok",
  Rejected: "badge-danger",
  Pending: "badge-warn",
};

// Map the API batch status (draft·sent·approved·changes_requested) to the UI label the Sendout
// Batch + Campaign surfaces render. draft/sent are both "Pending" (awaiting the client decision).
export function uiBatchStatus(s: string): Batch["status"] {
  if (s === "approved") return "Approved";
  if (s === "changes_requested") return "Rejected";
  return "Pending";
}
// API batch → the workspace `Batch` view model. ISO datetimes are trimmed to YYYY-MM-DD so the
// existing fmtShortDate/daysAgoLabel helpers read them.
export function batchFromApi(b: BatchApi): Batch {
  return {
    id: b.id,
    name: b.name,
    count: b.total,
    approved: b.approved,
    icp: b.icp || "—",
    status: uiBatchStatus(b.status),
    // N38 — the viewer's LOCAL calendar date, not a raw .slice of the UTC string (which shows the
    // UTC day and drifts a day for a late-UTC-evening event in a +tz zone like HK).
    createdAt: localCalendarDate(b.created_at),
    sentAt: b.sent_at ? localCalendarDate(b.sent_at) : undefined,
    // Only an *approved* batch has an approval date; a changes_requested ("Rejected") batch is
    // decided but not approved, so it must not render "Approved <date>".
    approvedAt:
      b.status === "approved" && b.decided_at ? localCalendarDate(b.decided_at) : undefined,
  };
}

// A UTC instant → the viewer's LOCAL calendar date ("YYYY-MM-DD"); "" when unusable. Used so the
// batches UI groups/labels by the day the viewer actually saw, matching `daysAgoLabel` below.
export function localCalendarDate(iso: string | null | undefined): string {
  const d = parseUtc(iso);
  if (!d) return "";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
// Do-not-contact list, derived live from the client's Brief (§4 Exclusions & Guardrails) rather
// than from mock fixtures. The three exclusion fields are stored as free-form text in the brief
// doc, each row in the canonical "domain, name, website" format; `parseExclusionCsv` is the same
// parser the brief uses, so what shows here is exactly what the brief accepted. A "we have none"
// checkbox (noExclude*) zeroes its group. Suppressed everywhere — never in any batch or campaign.
export type ExclusionGroup = { tag: string; cls: string; entries: ExclRow[] };

const EXCLUSION_SOURCES: { key: keyof Brief; noKey: keyof Brief; tag: string; cls: string }[] = [
  { key: "excludeCustomers", noKey: "noExcludeCustomers", tag: "Customer", cls: "badge-info" },
  { key: "excludeDeals", noKey: "noExcludeDeals", tag: "Active deal", cls: "badge-warn" },
  { key: "doNotContact", noKey: "noDoNotContact", tag: "Competitor / DNC", cls: "badge-danger" },
];

export function exclusionsFromBrief(doc: BriefDoc | undefined): {
  groups: ExclusionGroup[];
  count: number;
} {
  const d = (doc ?? {}) as Partial<Brief>;
  const groups = EXCLUSION_SOURCES.map(({ key, noKey, tag, cls }) => {
    const skip = d[noKey] === true;
    const text = typeof d[key] === "string" ? (d[key] as string) : "";
    return { tag, cls, entries: skip ? [] : parseExclusionCsv(text).valid };
  });
  return { groups, count: groups.reduce((n, g) => n + g.entries.length, 0) };
}

// Meeting attendee emails from this client's Brief (§5 logistics) — the recipients the approval
// link can be sent to. Stored as free text (one per line or comma/semicolon/space-separated, with
// the same meetingsLand→attendeeEmails read-migration the brief form uses). Parsed into a deduped
// (case-insensitive), order-preserving list of syntactically valid addresses for the Sendout Batch
// "Send approval email" recipient dropdown — no free-text entry, so only Brief addresses are used.
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export function attendeeEmailsFromBrief(doc: BriefDoc | undefined): string[] {
  const d = (doc ?? {}) as Record<string, unknown>;
  const raw =
    (typeof d.attendeeEmails === "string" && d.attendeeEmails) ||
    (typeof d.meetingsLand === "string" && d.meetingsLand) ||
    "";
  const out: string[] = [];
  const seen = new Set<string>();
  for (const tok of raw.split(/[\s,;]+/)) {
    const e = tok.trim();
    const key = e.toLowerCase();
    if (EMAIL_RE.test(e) && !seen.has(key)) {
      seen.add(key);
      out.push(e);
    }
  }
  return out;
}

// Per-prospect approval decision (pending·approved·removed) → {label, badge class} for the
// Sendout Batch detail rows. Resolved through `decisionView` (below) — not consumed directly.
const DECISION_VIEW: Record<string, { label: string; cls: string }> = {
  approved: { label: "Approved", cls: "badge-ok" },
  removed: { label: "Removed", cls: "badge-danger" },
  pending: { label: "Pending", cls: "badge-warn" },
};

// The approval cell for one prospect, resolved against its batch status. A Rejected (changes-
// requested) batch has NO per-prospect verdict — every row stays `pending` in the data so a re-send
// can re-open the same rows — but showing "Pending" next to a Rejected batch is contradictory, so a
// still-pending prospect under a rejected batch reads "Rejected". Approved/removed rows keep their
// own decision.
export function decisionView(
  decision: string,
  batchStatus: Batch["status"]
): { label: string; cls: string } {
  if (batchStatus === "Rejected" && decision === "pending") {
    return { label: "Rejected", cls: "badge-danger" };
  }
  return DECISION_VIEW[decision] || { label: decision, cls: "badge-neutral" };
}

export const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
export function clearScoring(setScoring: ScoringSetter, ids: string[]) {
  if (!ids.length) return;
  setScoring((prev) => {
    const next = new Set(prev);
    ids.forEach((id) => next.delete(id));
    return next;
  });
}

// Locked pricing constant (USD) — backend-development-plan §6.11 / §7. Supersedes the old
// HKD 6,000 + HKD 4,000 model. The rate is a fixed business rule, not per-client data.
export const PER_MEETING_USD = 500;

// S27 — meeting-outcome → display label + badge class. One source for the billing ledger, the
// meeting recaps, and the performance-summary calendar (which reads `.label` only).
export const OUTCOME_BADGE: Record<string, { label: string; badge: string }> = {
  qualified: { label: "Qualified", badge: "badge-ok" },
  short_call: { label: "Short call", badge: "badge-warn" },
  noshow: { label: "No-show", badge: "badge-danger" },
};

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function fmtShortDate(iso: string) {
  const [, m, d] = iso.split("-").map(Number);
  return MONTHS[m - 1] + " " + d;
}
export function daysAgoLabel(iso: string, now: Date = new Date()) {
  // N38 — compare LOCAL calendar days: anchor both the date and `now` at LOCAL midnight so the
  // label doesn't drift by the viewer's UTC offset (an event "today" in HK isn't "1 day ago").
  const [y, m, d] = iso.split("-").map(Number);
  if (!y || !m || !d) return "";
  const then = new Date(y, m - 1, d).getTime();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const diff = Math.round((today - then) / 86400000);
  return diff <= 0 ? "today" : diff === 1 ? "1 day ago" : diff + " days ago";
}

// Who the client sells to — drives the B2B/B2C market hard gate in company fit scoring. The stored
// value must be exactly B2B / B2C / Both (the gate matches on it); labels carry the plain-language
// hint. "Both" (or unset) disables the gate.
export const TARGET_MARKET_OPTS: { value: string; label: string }[] = [
  { value: "B2B", label: "B2B · we sell to businesses" },
  { value: "B2C", label: "B2C · we sell to consumers" },
  { value: "Both", label: "Both" },
];

export const SENIORITY_OPTS = ["C-level", "VP", "Director", "Manager", "Individual contributor"];
export const LANGUAGE_OPTS = ["English", "Mandarin", "Spanish", "French", "German", "Other"];
export const CYCLE_OPTS = ["Less than 1 month", "1–3 months", "3–6 months", "6+ months"];
export const MATURITY_OPTS = ["Startup", "Growth", "SME", "Enterprise", "Any"];
export const TONE_OPTS = ["Formal", "Professional & friendly", "Casual", "Let us recommend"];
export const CHANNEL_OPTS = ["Slack", "WhatsApp", "Email", "Other"];

export const blankFields = (): IcpFields => ({
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
export const blankBrief = (): Brief => ({
  companyName: "",
  website: "",
  sell: "",
  targetMarket: "",
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

export const blankIcp = (): Icp => ({
  short: "ICP A",
  tag: "",
  persona: "",
  fields: blankFields(),
});

// The ICP card model ⇄ the API's {name, tag, data} document (persona + fields live in data).
export const icpToApi = (icp: Icp) => ({
  name: icp.short,
  tag: icp.tag,
  data: { persona: icp.persona, fields: icp.fields },
});
export const apiToIcp = (a: IcpApi): Icp => {
  const d = (a.data ?? {}) as { persona?: string; fields?: Partial<IcpFields> };
  return {
    id: a.id,
    short: a.name,
    tag: a.tag,
    persona: d.persona ?? "",
    fields: { ...blankFields(), ...(d.fields ?? {}) },
  };
};

// "50–500" / "50+" / "up to 500" / null, with an optional value formatter (e.g. USD).
export function rangeText(r: Range, fmt: (n: number) => string = (n) => `${n}`): string | null {
  const lo = r?.min,
    hi = r?.max;
  if (lo != null && hi != null) return `${fmt(lo)}–${fmt(hi)}`;
  if (lo != null) return `${fmt(lo)}+`;
  if (hi != null) return `up to ${fmt(hi)}`;
  return null;
}
export const usd = (n: number) => "$" + n.toLocaleString("en-US");
// Apollo employee ranges are comma-strings ("10,100"); show them as a readable band ("10–100").
export const empBand = (r: string) => {
  const [lo, hi] = (r ?? "").split(",").map((x) => x.trim());
  if (!lo) return "";
  return hi ? `${lo}–${hi}` : `${lo}+`;
};
// Apollo facet machine value → display label: drop a leading "master_", underscores → spaces,
// Title-case, with the few acronym/hyphen fixups the server's _facet_label also applies.
export function humanizeFacet(value: string): string {
  if (value === "c_suite") return "C-Suite";
  if (value === "vp") return "VP";
  const text = value.startsWith("master_") ? value.slice("master_".length) : value;
  return text.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}
// Stage-1 business-model chip (B2B · B2C · Complex · Unknown) shown in the Step-1 company table.
// A factual label from `company_fit` — `Complex` = marketplace / B2B2C / platform serving both
// sides (e.g. Amazon). Colors are categorical, NOT a verdict (the fit chip carries the verdict; the
// gate reason explains an exclusion). Unlabeled ("") rows are pre-label — a rescore fills them.
const BUSINESS_MODEL_CHIP: Record<string, { label: string; cls: string }> = {
  B2B: { label: "B2B", cls: "badge-ok" },
  B2C: { label: "B2C", cls: "badge-warn" },
  Complex: { label: "Complex", cls: "badge-info" },
  Unknown: { label: "Unknown", cls: "badge-neutral" },
};
export function businessModelChip(value: string): { label: string; cls: string } {
  return BUSINESS_MODEL_CHIP[value] ?? { label: value, cls: "badge-neutral" };
}

// --- Scoring v2 (docs/initial-build-plan.md §D+.2) — the 4-label system ------
// Chip text/color + sort rank per label. `rank` orders the list feed (spec §11): actions first,
// footnotes last. A null label = "needs re-score" — ranked between the actionable and the collapsed
// buckets (rank 1.5) so it stays visible and prompts a score, never buried.
export const LABEL_META: Record<ScoreLabel, { text: string; cls: string; rank: number }> = {
  contact_now: { text: "Contact now", cls: "label-chip--now", rank: 0 },
  contact_soon: { text: "Contact soon", cls: "label-chip--soon", rank: 1 },
  low_fit: { text: "Low fit", cls: "label-chip--low", rank: 2 },
  excluded_by_rules: { text: "Excluded", cls: "label-chip--excluded", rank: 3 },
};
const UNSCORED_RANK = 1.5; // null label sits between contact_soon and low_fit

function labelRank(label: ScoreLabel | null): number {
  return label ? LABEL_META[label].rank : UNSCORED_RANK;
}

// Human labels for the four subscore axes (both tiers) — the subscore-bar segment tooltips.
export const AXIS_LABEL: Record<string, string> = {
  deal_fit: "Deal fit",
  outbound_gap: "Outbound gap",
  trigger: "Trigger",
  reachability: "Reachability",
  persona_fit: "Persona fit",
  authority: "Authority",
};
// Per-tier subscore axis ORDER for the 4-segment SubscoreBar (matches the backend
// SUBSCORE_AXES / SUBSCORE_AXES_PEOPLE in labeling.py). Company scores the deal; a person
// inherits the company label but scores their own persona/authority.
export const COMPANY_AXES = ["deal_fit", "outbound_gap", "trigger", "reachability"] as const;
export const PROSPECT_AXES = ["persona_fit", "authority", "trigger", "reachability"] as const;

// List-feed comparator (both companies + prospects carry label/score_total): label rank, then
// higher score_total first within a bucket, then newest. Replaces the v1 fit_score comparator.
export function compareByLabel(
  a: { label: ScoreLabel | null; score_total: number | null; created_at: string | null },
  b: { label: ScoreLabel | null; score_total: number | null; created_at: string | null }
): number {
  const r = labelRank(a.label) - labelRank(b.label);
  if (r !== 0) return r;
  const sa = a.score_total ?? -1;
  const sb = b.score_total ?? -1;
  if (sa !== sb) return sb - sa;
  return (b.created_at ?? "").localeCompare(a.created_at ?? "");
}

// The two collapsed buckets (spec §11) — shown as one summary count row, expandable.
export const COLLAPSED_LABELS: ScoreLabel[] = ["low_fit", "excluded_by_rules"];

// The list-feed bucket render order (spec §11): the two action buckets, then the not-yet-scored
// rows, then the two collapsed footnotes. `null` labels group under the "unscored" key (groupByLabel).
export const BUCKET_ORDER: (ScoreLabel | "unscored")[] = [
  "contact_now",
  "contact_soon",
  "unscored",
  "low_fit",
  "excluded_by_rules",
];
// Group-header text per bucket (LABEL_META covers the four labels; the null bucket needs its own).
export const BUCKET_HEAD: Record<ScoreLabel | "unscored", string> = {
  contact_now: "Contact now",
  contact_soon: "Contact soon",
  unscored: "Needs score",
  low_fit: "Low fit",
  excluded_by_rules: "Excluded by rules",
};

// Group a set of rows by label (null → the "unscored" key), preserving per-bucket order.
export function groupByLabel<T extends { label: ScoreLabel | null }>(
  rows: T[]
): Map<ScoreLabel | "unscored", T[]> {
  const out = new Map<ScoreLabel | "unscored", T[]>();
  for (const r of rows) {
    const key = r.label ?? "unscored";
    (out.get(key) ?? out.set(key, []).get(key)!).push(r);
  }
  return out;
}

// Compact currency / growth formatters for the Enrichment cell.
export function fmtRevenue(n: number | null): string {
  if (!n || n <= 0) return "";
  if (n >= 1e9) return `$${(n / 1e9).toFixed(n >= 1e10 ? 0 : 1)}B`;
  if (n >= 1e6) return `$${(n / 1e6).toFixed(n >= 1e7 ? 0 : 1)}M`;
  if (n >= 1e3) return `$${Math.round(n / 1e3)}K`;
  return `$${n}`;
}
export function fmtGrowth(f: number | null): string {
  if (f == null) return "";
  const pct = f * 100;
  return `${pct > 0 ? "+" : ""}${pct.toFixed(1)}%`;
}

export const EXCL_PLACEHOLDER = "tryholdslot.com, HoldSlot, https://tryholdslot.com/";

// CSV import: field key → the brief text field it fills, plus sane upload guards.
export const EXCL_TEXT_KEY: Record<
  "customers" | "deals" | "doNotContact",
  "excludeCustomers" | "excludeDeals" | "doNotContact"
> = {
  customers: "excludeCustomers",
  deals: "excludeDeals",
  doNotContact: "doNotContact",
};
export const MAX_CSV_BYTES = 1_000_000; // 1 MB
export const MAX_CSV_ROWS = 5000;

// The Step-1 manual scope override lives server-side now (per (tenant, ICP)); the old localStorage
// `loadScopeOverride`/`saveScopeOverride` pair + its `SCOPE_KEY` were retired in D+.5/R25, and the
// one-time U1.6 migration shim that lifted any leftover local entry to the server was removed in
// Wave 5 (S2) once every operator browser carried the done-flag (pre-flight-confirmed, 2026-07-13).
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

// Resolve the AI spec's targeting block for display/settings seeding. A v4 spec carries one block
// per ICP (`icp_targeting`) — `icpId` picks it, falling back to the first block so a summary is
// never blank; a spec with no blocks yields {}. Display-side only: the server's strict per-ICP
// resolution (400 on ambiguity) lives in targeting_for_icp.
function specTargetingBlock(
  spec: ResearchSpecResult | null,
  icpId?: string
): Record<string, unknown> {
  const sp = (spec?.spec ?? {}) as Record<string, unknown>;
  const blocks = sp.icp_targeting as Record<string, unknown>[] | undefined;
  if (!blocks?.length) return {}; // no blocks (or no spec) → nothing to seed
  if (icpId) {
    const hit = blocks.find((b) => b.icp_id === icpId);
    if (hit) return hit;
  }
  return blocks[0];
}

// The scope find-company would use right now: the manual override if set, else the AI spec's
// blocks (the `icpId` ICP's own block on a v4 multi-ICP spec).
export function effectiveScope(
  override: ScopeOverride | null,
  spec: ResearchSpecResult | null,
  icpId?: string
): ScopeOverride {
  if (override) return override;
  const sp = specTargetingBlock(spec, icpId) as {
    company_search_params?: Record<string, unknown>;
    intent_filters?: Record<string, unknown>;
  };
  return {
    company_search_params: sp.company_search_params ?? {},
    intent_filters: sp.intent_filters ?? {},
  };
}
export function scopeToForm(o: ScopeOverride): ScopeForm {
  const cs = (o.company_search_params ?? {}) as Record<string, unknown>;
  const c = ((o.intent_filters as { company?: Record<string, unknown> })?.company ?? {}) as Record<
    string,
    unknown
  >;
  const rev = (cs.revenue_range ?? {}) as { min?: number | null; max?: number | null };
  return {
    keywords: arrToCsv(cs.q_organization_keyword_tags),
    sizes: Array.isArray(cs.organization_num_employees_ranges)
      ? (cs.organization_num_employees_ranges as string[]).join("; ")
      : "",
    locations: arrToCsv(cs.organization_locations),
    revenueMin: rev.min != null ? String(rev.min) : "",
    revenueMax: rev.max != null ? String(rev.max) : "",
    hiringTitles: arrToCsv(c.q_organization_job_titles),
  };
}
export function formToOverride(f: ScopeForm): ScopeOverride {
  // No date windows here by design (spec v5): a stale saved override may still carry them, but
  // the server-side mapper drops them unconditionally, and a re-save through this form sheds them.
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
      },
    },
  };
}
// A one-line human read of the active scope — for the empty state + the 0-results toast.
export function scopeSummary(o: ScopeOverride): string {
  const cs = (o.company_search_params ?? {}) as Record<string, unknown>;
  const c = ((o.intent_filters as { company?: Record<string, unknown> })?.company ?? {}) as Record<
    string,
    unknown
  >;
  const arr = (v: unknown) => (Array.isArray(v) ? (v as string[]) : []);
  const parts: string[] = [];
  if (arr(cs.organization_locations).length) parts.push(arr(cs.organization_locations).join("/"));
  if (arr(cs.q_organization_keyword_tags).length)
    parts.push(arr(cs.q_organization_keyword_tags).join("/"));
  if (arr(cs.organization_num_employees_ranges).length)
    parts.push(`size ${arr(cs.organization_num_employees_ranges).join(", ")}`);
  if (arr(c.q_organization_job_titles).length)
    parts.push(`hiring ${arr(c.q_organization_job_titles).join("/")}`);
  return parts.join(" · ");
}

// The 11 Management-Level values (Apollo's order). Static so the panel renders before counts load;
// department options come from the live facet probe (the ~245-value tree isn't duplicated here).
export const SENIORITY_OPTIONS: { value: string; label: string }[] = [
  "owner",
  "founder",
  "c_suite",
  "partner",
  "vp",
  "head",
  "director",
  "manager",
  "senior",
  "entry",
  "intern",
].map((value) => ({ value, label: humanizeFacet(value) }));
// The 14 master Department & Job Function options are fetched from the backend (getPeopleDepartments)
// — the single source of truth is Apollo's taxonomy in research_spec.py, never duplicated here — so
// the panel can render the AI-scope departments before the live facet probe loads; the ~245-value
// subdepartment tree (counts + expandable subs) still comes from the probe once companies are ticked.
// The Step-2 people scope override is persisted SERVER-SIDE (per tenant), not in localStorage, so a
// saved tuning follows the operator across browsers and a schema change can't leave a stale local
// entry shadowing the AI scope. Load/save/reset go through the API (get/put/deletePeopleScopeOverride).
export function effectivePeopleScope(
  override: PeopleScopeOverride | null,
  spec: ResearchSpecResult | null,
  icpId?: string
): PeopleScopeOverride {
  if (override) return override;
  const sp = specTargetingBlock(spec, icpId) as {
    people_search_params?: Record<string, unknown>;
  };
  return { people_search_params: sp.people_search_params ?? {} };
}
const _arr = (v: unknown): string[] => (Array.isArray(v) ? (v as string[]) : []);
export function peopleScopeToForm(o: PeopleScopeOverride): PeopleScopeForm {
  const ps = (o.people_search_params ?? {}) as Record<string, unknown>;
  return {
    seniorities: _arr(ps.person_seniorities),
    departments: _arr(ps.person_department_or_subdepartments),
  };
}
export function formToPeopleOverride(f: PeopleScopeForm): PeopleScopeOverride {
  return {
    people_search_params: {
      person_seniorities: f.seniorities,
      person_department_or_subdepartments: f.departments,
    },
  };
}
export function peopleScopeSummary(o: PeopleScopeOverride): string {
  const ps = (o.people_search_params ?? {}) as Record<string, unknown>;
  const parts: string[] = [];
  if (_arr(ps.person_seniorities).length)
    parts.push(_arr(ps.person_seniorities).map(humanizeFacet).join("/"));
  if (_arr(ps.person_department_or_subdepartments).length)
    parts.push(_arr(ps.person_department_or_subdepartments).map(humanizeFacet).join("/"));
  return parts.join(" · ");
}

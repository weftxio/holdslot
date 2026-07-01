import {
  type BatchApi,
  type BriefDoc,
  type IcpApi,
  type ProspectApi,
  type ResearchSpecResult,
} from "@/lib/api";
import { type ExclRow, parseExclusionCsv } from "@/lib/csv";
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
// People that still need enrichment (no verified email yet) vs. enriched-and-ready-to-batch.
export const NEEDS_ENRICH = new Set(["found", "confirmed", "score_error"]);
export const ENRICHED_STATUS = "scored";
// Prospect-list ordering: Enriched (status `scored`) first, then AI Score (highest → lowest,
// unscored sink), then remaining status (Found before anything else).
const STATUS_SORT: Record<string, number> = { scored: 0, found: 1 };
export function compareProspectRows(a: ProspectApi, b: ProspectApi): number {
  const ae = a.status === ENRICHED_STATUS ? 0 : 1;
  const be = b.status === ENRICHED_STATUS ? 0 : 1;
  if (ae !== be) return ae - be; // Enriched on top
  const sa = a.fit_score ?? -1;
  const sb = b.fit_score ?? -1;
  if (sb !== sa) return sb - sa; // then AI Score desc
  return (STATUS_SORT[a.status] ?? 2) - (STATUS_SORT[b.status] ?? 2);
}
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
    createdAt: (b.created_at ?? "").slice(0, 10),
    sentAt: b.sent_at ? b.sent_at.slice(0, 10) : undefined,
    // Only an *approved* batch has an approval date; a changes_requested ("Rejected") batch is
    // decided but not approved, so it must not render "Approved <date>".
    approvedAt: b.status === "approved" && b.decided_at ? b.decided_at.slice(0, 10) : undefined,
  };
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

// The mock reply fixtures are dated relative to this fixed "today"; pass it to daysAgoLabel for
// those. Live data (e.g. Phase D batches) leaves the arg off and gets the real current date.
const TODAY_ISO = "2026-06-03";
export const MOCK_TODAY = new Date(TODAY_ISO + "T00:00:00Z");
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
export function fmtShortDate(iso: string) {
  const [, m, d] = iso.split("-").map(Number);
  return MONTHS[m - 1] + " " + d;
}
export function daysAgoLabel(iso: string, now: Date = new Date()) {
  const diff = Math.round((now.getTime() - new Date(iso + "T00:00:00Z").getTime()) / 86400000);
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
// A YYYY-MM-DD min/max window → "2025-12-22 → 2026-06-22" / "from …" / "until …" / null.
export function dateRange(r?: { min?: string | null; max?: string | null }): string | null {
  const lo = r?.min,
    hi = r?.max;
  if (lo && hi) return `${lo} → ${hi}`;
  if (lo) return `from ${lo}`;
  if (hi) return `until ${hi}`;
  return null;
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

// AI Score cell — a clean fit chip (4 tier colors) + a hover/focus info tooltip carrying the
// "why a fit" reason. Reason is rendered as JSX text (never innerHTML).
export const FIT_CHIP: Record<string, string> = {
  Strong: "fit-chip--strong",
  Good: "fit-chip--good",
  Moderate: "fit-chip--moderate",
  Below: "fit-chip--below",
};

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

const SCOPE_KEY = (client: string) => `holdslot_scope_${client}`;
export function loadScopeOverride(client: string): ScopeOverride | null {
  if (typeof window === "undefined") return null;
  try {
    const v = JSON.parse(localStorage.getItem(SCOPE_KEY(client)) || "null");
    return v && typeof v === "object" ? (v as ScopeOverride) : null;
  } catch {
    return null;
  }
}
export function saveScopeOverride(client: string, v: ScopeOverride | null) {
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
export function effectiveScope(
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
export function scopeToForm(o: ScopeOverride): ScopeForm {
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
export function formToOverride(f: ScopeForm): ScopeOverride {
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
export function scopeSummary(o: ScopeOverride): string {
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
  spec: ResearchSpecResult | null
): PeopleScopeOverride {
  if (override) return override;
  const sp = (spec?.spec ?? {}) as { people_search_params?: Record<string, unknown> };
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

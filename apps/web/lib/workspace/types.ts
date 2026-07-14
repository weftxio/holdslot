// ICP (section 2) + Personas (section 3), held per profile
export type IcpFields = {
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
export type Icp = { id?: string; short: string; tag: string; persona: string; fields: IcpFields };
// Global brief sections (1, 4, 5, 6, 7) — filled once
export type Brief = {
  companyName: string;
  website: string;
  sell: string;
  targetMarket: string;
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
// Live (Phase D) — `id` is the batch id used for detail/send/decide calls. `status` is the UI
// label mapped from the API's draft/sent/approved/changes_requested (see batchFromApi).
export type Batch = {
  id: string;
  name: string;
  count: number;
  approved: number;
  icp: string;
  status: "Approved" | "Pending" | "Rejected";
  createdAt: string;
  sentAt?: string;
  approvedAt?: string;
};
// A `Set<string>` state updater (the "Scoring…" row sets). Typed loosely so the reconcile helpers
// below can live at module scope and serve both the company and people scorers.
export type ScoringSetter = (updater: (prev: Set<string>) => Set<string>) => void;

// A meeting-summary card. Derived from a held `meeting` row (F5); the detail fields
// (Attendees/Discussed/Next step/Sentiment/Recording) stay pending until the LLM summary lands (FD-8).
export type Recap = {
  id: string;
  campaign: string;
  campaignId: string | null; // M27 — filter recaps by id, not the non-unique campaign name
  batch: string;
  prospectName: string;
  companyName: string;
  scheduledAt: string;
  outcome: string | null;
  rating: number | null;
  disputed: boolean; // M33 — the current dispute flag (shown + toggled by the outcome-correction UI)
  // tri-state (NF-3): true = deal won · false = no deal · null = not yet decided. Kept nullable so
  // the §11 adopter-vs-churn read never conflates "explicitly no deal" with "undecided".
  won: boolean | null;
};

export type Range = { min?: number | null; max?: number | null } | undefined;

// ---- Find-company scope override (Settings modal) -----------------------------------------
// A manual override of the AI scope's Apollo company-search filters, persisted per client in
// localStorage and passed verbatim to find-company. `null` = use the saved spec unchanged.
export type ScopeOverride = {
  company_search_params: Record<string, unknown>;
  intent_filters: Record<string, unknown>;
};
// The editable shape — arrays are held as comma/semicolon text so they type naturally in inputs.
// The funding/jobs-posted date windows were removed entirely (spec v5): they always
// over-constrained the search, so they are gone from the form, the contract, and the mapper.
export type ScopeForm = {
  keywords: string;
  sizes: string;
  locations: string;
  revenueMin: string;
  revenueMax: string;
  hiringTitles: string;
};

// ---- Find-people scope override (Step-2 Settings modal) -----------------------------------
// Same pattern as the company scope: a per-client manual override of the AI scope's Apollo
// mixed_people/api_search filters. `organization_ids` is NOT here — the server sets it per selected
// org. `null` → use the saved spec's people_search_params.
export type PeopleScopeOverride = { people_search_params: Record<string, unknown> };
// The override now holds ONLY the two persona facets — Management Level (person_seniorities) ×
// Department/Job Function (person_department_or_subdepartments). Org-context filters
// (keyword/location/size) are dropped: find always pins one org, which fixes them anyway.
export type PeopleScopeForm = {
  seniorities: string[];
  departments: string[];
};

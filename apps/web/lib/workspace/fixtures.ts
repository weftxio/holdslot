import { type ExclRow } from "@/lib/csv";
import type { LedgerRow, Recap, Reply } from "./types";

// Per-prospect enrichment shown in the expanded Approval Batches table (mock — wired in Phase C/E).
// Mirrors the columns an external sourcing tool surfaces: a fit score (grade · intent heat),
// the prospect's industry, and which of the client's people they're connected to.
export const SCORE_TIERS = [
  { grade: "A", heat: "Burning", cls: "badge-ok" },
  { grade: "B", heat: "Warm", cls: "badge-warn" },
  { grade: "C", heat: "Cool", cls: "badge-neutral" },
] as const;
export const SAMPLE_INDUSTRIES = [
  "Artificial Intelligence",
  "Software",
  "Fintech",
  "Logistics",
  "Healthtech",
  "Retail",
  "Manufacturing",
  "Media",
];
export const SAMPLE_CONNECTIONS = [
  "Sam Blond",
  "Malay Desai",
  "Shek Viswanathan",
  "Tommy Hung",
  "Stan Rapp",
];
export const STAFF_ROLES = [
  "VP Sales",
  "Head of Ops",
  "RevOps Lead",
  "COO",
  "Marketing Dir.",
  "CTO",
  "Procurement",
];

export const LEDGER: LedgerRow[] = [
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

export const RECAPS: Recap[] = [
  { campaign: "Campaign 1", batch: "Batch 3", recId: "kfx-9d2a-bv1", won: true },
  { campaign: "Campaign 1", batch: "Batch 3", recId: "qmt-7r4c-zp8", won: false },
  { campaign: "Campaign 1", batch: "Batch 3", recId: "hla-2w6e-nk3", won: true },
];

// Per-mode copy for the reply card (inbound reply vs outbound follow-up nudge).
export const NUDGE_COPY = {
  qhead: "No reply yet",
  datePrefix: "last outreach ",
  body: "Prospect hasn't responded yet — a follow-up nudge is drafted and ready to send.",
  draftLabel: "Suggested follow-up",
  cta: "Send Follow-Up",
  done: "Follow-up nudge sent",
};
export const REPLY_COPY = {
  qhead: "Prospect replied",
  datePrefix: "",
  body: "",
  draftLabel: "Suggested reply",
  cta: "Send Reply",
  done: "Reply approved and sent",
};

export const INITIAL_REPLIES: Reply[] = [
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

// Do-not-contact list — the three exclusion sources from the Brief. Everyone here is
// suppressed from every batch and campaign; it is pinned to the top of Approval Batches
// for review and never overlaps a sendout batch.
// Each entry mirrors the Brief exclusion input format: company domain · company name · website.
export const EXCLUSIONS: {
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
export const EXCLUSION_COUNT = EXCLUSIONS.reduce((n, g) => n + g.entries.length, 0);

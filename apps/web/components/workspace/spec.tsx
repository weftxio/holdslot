"use client";
import { type ReactNode, useRef, useState } from "react";
import { createPortal } from "react-dom";
import clsx from "clsx";
import { Modal } from "@/components/Modal";
import {
  type CompanyEnrichment,
  type IcpSuggestion,
  type ResearchSpecResult,
  type ScopingPrompt,
  getScopingPrompt,
  saveScopingSystemPrompt,
} from "@/lib/api";
import type { ScoreLabel, Subscores } from "@/lib/api";
import type { Range } from "@/lib/workspace/types";
import {
  AXIS_LABEL,
  FIT_CHIP,
  LABEL_META,
  empBand,
  fmtGrowth,
  fmtRevenue,
  humanizeFacet,
  rangeText,
  usd,
} from "@/lib/workspace/constants";

// Read-only chips for a ResearchSpec value list (— when empty). Reuses the ICP card grammar.
// Quiet em-dash for an empty value (NOT the hatched `.ph` sample marker — a data field that
// the AI left blank is a normal state, so it reads as a muted dash, not a placeholder box).
function Dash() {
  return <span className="muted">—</span>;
}
// "Jul 9, 2:14 PM GMT+8" from an ISO instant, rendered in the VIEWER's own timezone; "" when unusable.
function whenLabel(iso?: string | null): string {
  if (!iso) return "";
  // A timezone-naive ISO string (no trailing Z / ±HH:MM — the Data API strips the offset off our
  // UTC timestamps) would otherwise be parsed as browser-LOCAL, showing the raw UTC digits. Pin it
  // to UTC so toLocaleString then converts it into the viewer's own zone.
  const hasTz = /[zZ]$/.test(iso) || /T.*[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  if (Number.isNaN(d.getTime())) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
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
export function SpecHead({ children }: { children: ReactNode }) {
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
// A plain text value, or the quiet muted dash when empty (0 and false are real values).
function Val({ children }: { children: ReactNode }) {
  return children == null || children === "" ? <Dash /> : <>{children}</>;
}

// --- Scoring v2 (docs/holdslot-scoring-spec-v2.md) — the 4-label UI pieces ----

// The label chip (spec §11) — replaces the 0–100 AI Score chip. Shows the label + the 4–20 total
// when scored. Chip text/color come from LABEL_META; the ICP badge is folded in separately.
export function LabelChip({ label, score }: { label: ScoreLabel; score?: number | null }) {
  const m = LABEL_META[label];
  return (
    <span className={clsx("label-chip", m.cls)}>
      {m.text}
      {score != null ? ` · ${score}` : ""}
    </span>
  );
}

// The 4-segment subscore bar (spec §11) — a compact equalizer, one segment per axis filled to its
// 1–5 value, each segment tooltip'd with its axis name + value. `axes` is the tier's axis order.
export function SubscoreBar({
  subscores,
  axes,
}: {
  subscores: Subscores;
  axes: readonly string[];
}) {
  return (
    <span className="subscore-bar" role="img" aria-label="subscores">
      {axes.map((ax) => {
        const v = Math.max(1, Math.min(subscores?.[ax] ?? 1, 5));
        return (
          <span key={ax} className="subscore-seg" title={`${AXIS_LABEL[ax] ?? ax}: ${v}/5`}>
            <span className="subscore-fill" style={{ height: `${(v / 5) * 100}%` }} />
          </span>
        );
      })}
    </span>
  );
}

// Non-blocking flag marker (spec §10) — a small warn glyph + count; the full flag list is the
// tooltip. Renders nothing when a row has no flags.
export function FlagMarker({ flags }: { flags: string[] }) {
  if (!flags?.length) return null;
  return (
    <span className="flag-marker" title={flags.join(", ")} aria-label={`${flags.length} flags`}>
      ⚑ {flags.length}
    </span>
  );
}

export function FitScore({
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

// Enrichment cell — the 8 Apollo-enrich study fields. The cell shows a compact, truncated view;
// hovering/focusing it opens a portaled popup with the FULL untruncated content (the popup is
// fixed-positioned + portaled to <body> so the scrolling table body never clips it). It flips above
// the row when the row sits in the lower half of the viewport. All values are JSX text, no innerHTML.
export function CompanyStudy({ e }: { e: CompanyEnrichment }) {
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

// Clickable company site for the merged Domain+Website cell: shows the short domain as the label
// and links to the full website (falls back to the domain when no website is known). Both are
// user/CSV-sourced strings, so render the label as JSX text and force a safe scheme.
export function WebLink({ website, domain }: { website?: string; domain?: string }) {
  const label = domain || website || "";
  const target = website || domain || "";
  if (!label) return <span className="muted">—</span>;
  const href = /^https?:\/\//i.test(target) ? target : `https://${target.replace(/^\/+/, "")}`;
  return (
    <a className="weblink" href={href} target="_blank" rel="noopener noreferrer">
      {label} ↗
    </a>
  );
}

// LinkedIn glyph link for a person; nothing rendered when no profile is known.
export function LinkedInLink({ url }: { url?: string }) {
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

// One per-ICP targeting block of the ResearchSpec (v4), or the v3 legacy single block (no
// icp_id/icp_name). Exact Apollo request fields — see research_spec.py.
type SpecTargetingBlock = {
  icp_id?: string;
  icp_name?: string;
  // UTC ISO 8601 build time of THIS block (server-stamped, per ICP). In a selective re-scope an
  // un-touched ICP keeps its earlier stamp; absent only on old pre-stamp specs (then no time shows,
  // never a borrowed/shared one — the UI reads this field alone).
  generated_at?: string;
  company_search_params?: {
    q_organization_keyword_tags?: string[];
    organization_num_employees_ranges?: string[];
    organization_locations?: string[];
    revenue_range?: Range;
  };
  people_search_params?: {
    person_seniorities?: string[];
    person_department_or_subdepartments?: string[];
    q_keywords?: string;
    organization_locations?: string[];
    organization_num_employees_ranges?: string[];
  };
  // v5: intent = hiring titles only (the funding/jobs-posted date windows were removed — they
  // always over-constrained the search; old specs may still carry them but they're never shown
  // or sent).
  intent_filters?: {
    company?: {
      q_organization_job_titles?: string[];
    };
  };
};

// The three review grids (company / people / intent) for ONE targeting block. A v4 block is
// headed by its ICP name (multi-ICP scopes render one group per profile); the v3 single block
// keeps the original unnamed headings. `hideName` drops the ICP-name prefix on the inner
// headings when the block is wrapped in a collapsible whose header already names the ICP.
function TargetingSections({ b, hideName }: { b: SpecTargetingBlock; hideName?: boolean }) {
  const cs = b.company_search_params ?? {};
  const ppl = b.people_search_params ?? {};
  const intent = b.intent_filters?.company ?? {};
  const head = (label: string) => (b.icp_name && !hideName ? `${b.icp_name} · ${label}` : label);
  return (
    <>
      <SpecHead>{head("Company search · firmographics")}</SpecHead>
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

      <SpecHead>{head("People search · personas (Management Level × Department)")}</SpecHead>
      <div className="icp-grid">
        <SpecCell label="Management level">
          <SpecChips items={(ppl.person_seniorities ?? []).map(humanizeFacet)} />
        </SpecCell>
        <SpecCell label="Departments &amp; job function">
          <SpecChips
            items={(ppl.person_department_or_subdepartments ?? []).map(humanizeFacet)}
          />
        </SpecCell>
        <SpecCell label="Industry keywords">
          <Val>{ppl.q_keywords}</Val>
        </SpecCell>
        <SpecCell label="Locations (HQ)">
          <SpecChips items={ppl.organization_locations} />
        </SpecCell>
        <SpecCell label="Company size">
          <SpecChips items={(ppl.organization_num_employees_ranges ?? []).map(empBand)} />
        </SpecCell>
      </div>

      <SpecHead>{head("Intent signals · hiring")}</SpecHead>
      <div className="icp-grid">
        <SpecCell label="Hiring for">
          <SpecChips items={intent.q_organization_job_titles} />
        </SpecCell>
      </div>
    </>
  );
}

// The LLM-generated ResearchSpec, rendered for operator review with existing classes only.
// Always rendered: the Structure/Re-structure control lives in this panel's header, so the
// first spec is generated from here too. Before any spec exists, an empty state is shown.
export function SpecReview({
  client,
  spec,
  structuring,
  saving,
  ready,
  onStructure,
  onAcceptIcp,
  icps = [],
}: {
  client: string;
  spec: ResearchSpecResult | null;
  structuring: boolean;
  saving: boolean;
  ready: boolean;
  // `icpIds` restricts the run to those ICP profiles (a selective re-scope); empty → every ICP.
  onStructure: (icpIds: string[]) => void;
  onAcceptIcp: (s: IcpSuggestion) => void;
  // The client's ICP profiles (id + display name) — drives the panel's ICP filter even when the
  // stored scope predates per-ICP generation (a legacy scope has no blocks to derive names from).
  icps?: { id: string; name: string }[];
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
      // The previewed INPUT is always the full brief + every ICP — the live Generate sends the
      // same, and there is no per-ICP review lens.
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
  // The ResearchSpec shape — exact Apollo request fields, rendered field-by-field so the operator
  // can review every parameter the LLM produced before Phase C's Apollo search (see
  // research_spec.py). v4 carries `icp_targeting` (ONE block per ICP — rendered as one section
  // group per profile); a v3 spec's single top-level block renders as one unnamed group until the
  // next regenerate. `icp_validation` is the paying-customer read; `credit_policy` is server-set,
  // not AI.
  const s = (spec?.spec ?? {}) as {
    icp_targeting?: SpecTargetingBlock[];
    // v3 legacy — single top-level block
    company_search_params?: SpecTargetingBlock["company_search_params"];
    people_search_params?: SpecTargetingBlock["people_search_params"];
    intent_filters?: SpecTargetingBlock["intent_filters"];
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
  // v4 → one section group per ICP block; v3 → the single merged block as one unnamed group.
  const blocks: SpecTargetingBlock[] = s.icp_targeting?.length
    ? s.icp_targeting
    : [
        {
          company_search_params: s.company_search_params,
          people_search_params: s.people_search_params,
          intent_filters: s.intent_filters,
        },
      ];
  // Per-ICP coverage badges (which profiles this scope covers). Options come from the client's
  // live ICP list, with the blocks' own echoed names as fallback when the caller passes none.
  const isPerIcp = Boolean(s.icp_targeting?.length);
  const blockNames = new Map(
    blocks
      .filter((b) => b.icp_id && b.icp_name)
      .map((b) => [b.icp_id as string, b.icp_name as string])
  );
  const icpOptions = icps.length
    ? icps
    : [...blockNames].map(([id, name]) => ({ id, name }));
  // Every block is rendered; each ICP's detail is individually collapsible (default collapsed —
  // `openScopes` starts empty, so the scope opens with every ICP's targeting folded away).
  const shownBlocks = blocks;
  const [openScopes, setOpenScopes] = useState<Set<string>>(new Set());
  const toggleScope = (key: string) =>
    setOpenScopes((prev) => {
      const next = new Set(prev);
      next.has(key) ? next.delete(key) : next.add(key);
      return next;
    });
  // Which ICP profiles the next AI Scoping run regenerates (checkbox per ICP row). Empty = every
  // ICP (a full generation). Ids that no longer exist are filtered out at run time.
  const [selectedIcps, setSelectedIcps] = useState<Set<string>>(new Set());
  const toggleSelect = (id: string) =>
    setSelectedIcps((prev) => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  const val = s.icp_validation ?? {};
  const profiles = val.customer_profiles ?? [];
  const cp = s.credit_policy ?? {};
  const blocked = structuring || saving || !ready;
  // Per-ICP rows drive the collapsible list AND the selection: shown when the client has ICP
  // profiles and the scope is per-ICP (v4) — or before any scope exists, so a freshly-created ICP
  // reads as "No AI scope yet" and can be generated on its own. A legacy v3 (merged) spec falls
  // back to the unnamed merged block(s) below.
  const showPerIcp = icpOptions.length > 0 && (isPerIcp || !spec);
  const perIcpRows = icpOptions.map((o) => ({
    id: o.id,
    name: o.name,
    block: blocks.find((b) => (b.icp_id ?? "") === o.id) ?? null,
  }));
  const selectedList = icpOptions.filter((o) => selectedIcps.has(o.id)).map((o) => o.id);
  const runScoping = () => onStructure(selectedList);
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
                  : selectedList.length
                    ? "Regenerate the AI scope for only the selected ICP(s)."
                    : "Summarize this brief with AI into a prospect scope for every ICP."
              }
            >
              <button
                type="button"
                className="btn btn-accent btn-sm"
                disabled={blocked}
                style={blocked ? { pointerEvents: "none" } : undefined}
                onClick={runScoping}
              >
                {structuring ? "Generating…" : "AI Scoping"}
              </button>
            </span>
          </div>
          {/* Time-demand note while running; otherwise a one-line reminder of what the next run
              covers — the selected ICP(s), or every ICP when none are ticked. */}
          {structuring ? (
            <div
              className="ph-sub"
              style={{ fontSize: 11.5, textAlign: "right", whiteSpace: "nowrap" }}
            >
              {selectedList.length > 1
                ? `⏱ Generating… ~1 min per ICP · runs in the background, keep working`
                : `⏱ Generating… ~1 min · runs in the background, keep working`}
            </div>
          ) : showPerIcp ? (
            <div
              className="ph-sub"
              style={{ fontSize: 11.5, textAlign: "right", whiteSpace: "nowrap" }}
            >
              {selectedList.length
                ? `Scopes ${selectedList.length} selected ICP${
                    selectedList.length > 1 ? "s, one at a time" : ""
                  }`
                : "Scopes every ICP · tick ICPs below to scope only those"}
            </div>
          ) : null}
        </div>
      </div>
      <div className="panel-pad">
        {showPerIcp ? (
          // One collapsible per ICP profile: the name + an AI-scope status badge head each row, and
          // a checkbox ticks it for the next AI Scoping run. Rows WITH a generated block expand to
          // the targeting detail (folded by default); rows without read "No AI scope yet".
          perIcpRows.map((row) => {
            const open = openScopes.has(row.id);
            const has = Boolean(row.block);
            const checked = selectedIcps.has(row.id);
            // This ICP block's OWN build time — never a shared fallback, so a re-scope of one ICP
            // can't make an untouched ICP look re-stamped. A block with no stamp (old pre-stamp
            // spec) shows no time until it's individually scoped.
            const when = has ? whenLabel(row.block?.generated_at) : "";
            return (
              <div className={clsx("scope-acc", open && has && "open")} key={row.id}>
                <div className="scope-acc-head">
                  <input
                    type="checkbox"
                    className="tbl-check"
                    checked={checked}
                    onChange={() => toggleSelect(row.id)}
                    title="Select this ICP for the next AI Scoping run"
                  />
                  <button
                    type="button"
                    className="scope-acc-toggle"
                    aria-expanded={open && has}
                    disabled={!has}
                    onClick={() => has && toggleScope(row.id)}
                  >
                    <span
                      className={clsx("scope-acc-caret", open && has && "open")}
                      aria-hidden="true"
                      style={{ visibility: has ? undefined : "hidden" }}
                    >
                      ▸
                    </span>
                    <span className="scope-acc-title">{row.name}</span>
                    <span className={"badge badge-" + (has ? "ok" : "warn")}>
                      {has ? "AI scope ✓" : "No AI scope yet"}
                    </span>
                    {has && (
                      <span className="scope-acc-hint">
                        {open ? "Hide targeting" : "Show targeting"}
                      </span>
                    )}
                  </button>
                  {when && (
                    <span className="scope-acc-when" title="When this ICP's scope was generated">
                      Generated {when}
                    </span>
                  )}
                </div>
                {open && has && (
                  <div className="scope-acc-body">
                    <TargetingSections b={row.block!} hideName />
                  </div>
                )}
              </div>
            );
          })
        ) : !spec ? (
          <div className="sum-empty">
            Not generated yet · fill in the brief, then generate your Apollo-ready scope.
          </div>
        ) : (
          // Legacy v3 (merged) or brief-only spec: the single unnamed block reads as one group.
          shownBlocks.map((b, i) => {
            const key = b.icp_id || `blk-${i}`;
            const open = openScopes.has(key);
            const title = b.icp_name || "Merged scope · applies to all ICPs";
            const when = whenLabel(b.generated_at);
            return (
              <div className={clsx("scope-acc", open && "open")} key={key}>
                <div className="scope-acc-head">
                  <button
                    type="button"
                    className="scope-acc-toggle"
                    aria-expanded={open}
                    onClick={() => toggleScope(key)}
                  >
                    <span className={clsx("scope-acc-caret", open && "open")} aria-hidden="true">
                      ▸
                    </span>
                    <span className="scope-acc-title">{title}</span>
                    <span className="scope-acc-hint">
                      {open ? "Hide targeting" : "Show targeting"}
                    </span>
                  </button>
                  {when && (
                    <span className="scope-acc-when" title="When this scope was generated">
                      Generated {when}
                    </span>
                  )}
                </div>
                {open && (
                  <div className="scope-acc-body">
                    <TargetingSections b={b} hideName />
                  </div>
                )}
              </div>
            );
          })
        )}

        {spec && (
          <>
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

          {/* Scoping gaps are NOT shown here — each is routed to the brief section that owns the
              missing input (see gapSection in brief/page.tsx) so the operator fixes it in place. */}
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
              {(sug.people_search_params?.person_seniorities?.length ?? 0) > 0 && (
                <div className="is-row">
                  <span className="k">Management level</span>
                  <SpecChips
                    items={(sug.people_search_params?.person_seniorities ?? []).map(humanizeFacet)}
                  />
                </div>
              )}
              {(sug.people_search_params?.person_department_or_subdepartments?.length ?? 0) > 0 && (
                <div className="is-row">
                  <span className="k">Departments</span>
                  <SpecChips
                    items={(
                      sug.people_search_params?.person_department_or_subdepartments ?? []
                    ).map(humanizeFacet)}
                  />
                </div>
              )}
            </div>
          ))}
          </>
        )}
      </div>
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
              <span className="badge badge-neutral">input · all ICPs</span>
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
              {/* RIGHT — Input prompt: read-only, the client brief + the ICP set selected in the
                  panel's ICP filter (narrowed = review lens; the live run sends every ICP). */}
              <div className="prompt-col">
                <div className="prompt-col-head">
                  <label>Input prompt</label>
                  <span className="ph-sub">read-only · brief + all ICPs</span>
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

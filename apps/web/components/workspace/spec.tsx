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
import type { Range } from "@/lib/workspace/types";
import {
  FIT_CHIP,
  dateRange,
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
      person_seniorities?: string[];
      person_department_or_subdepartments?: string[];
      q_keywords?: string;
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

          <SpecHead>People search · personas (Management Level × Department)</SpecHead>
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

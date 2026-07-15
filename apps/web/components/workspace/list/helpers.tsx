// Shared presentational atoms + pure helpers for the two Prospect-List step branches (2.4 Stage 3).
// Lifted verbatim from list/page.tsx so Step1Companies and Step2People can share them; bodies are
// byte-identical to the inline originals.
import type { CompanyApi, ScoreLabel, Subscores } from "@/lib/api";
import { COLLAPSED_LABELS } from "@/lib/workspace/constants";
import { LabelChip, SubscoreList } from "@/components/workspace";

// The two collapsed footnote buckets as a plain string set — COLLAPSED_LABELS is typed to
// ScoreLabel, but the bucket keys include the "unscored" (null-label) group, so membership is
// tested against strings.
export const COLLAPSED_KEYS = new Set<string>(COLLAPSED_LABELS);

// The row carries a non-empty subscore vector (a scored row) → render the 4-segment bar.
export const hasSubs = (s: Record<string, number> | undefined) => !!s && Object.keys(s).length > 0;
// The Step-1 company / Step-2 person score cell — one of three states: fit-scoring in progress, a
// resolved label (chip + subscores, plus an optional grey reason line the company table shows for
// non-contact buckets), or Pending. Extracted (S18) so both tables emit byte-identical markup.
export function FitCell({
  scoring,
  label,
  score,
  subscores,
  axes,
  reason,
}: {
  scoring: boolean;
  label: ScoreLabel | null;
  score: number | null;
  subscores: Subscores;
  axes: readonly string[];
  reason?: string | null;
}) {
  if (scoring)
    return (
      <span className="fit-scoring" title="AI fit-scoring in progress">
        <span className="hs-spinner" aria-hidden="true" />
        Scoring…
      </span>
    );
  if (!label) return <span className="muted">Pending</span>;
  return (
    <div className="ai-score-cell">
      <span className="label-line">
        <LabelChip label={label} score={score} />
      </span>
      {hasSubs(subscores) ? <SubscoreList subscores={subscores} axes={axes} /> : null}
      {reason ? (
        <span className="score-reason" title={reason}>
          {reason}
        </span>
      ) : null}
    </div>
  );
}
// The "Fetching…" spinner overlaid on a list body while a fetch is in flight (Step-1 + Step-2,
// S18) — renders nothing when idle so the caller can drop it in unconditionally.
export function ListOverlay({ busy }: { busy: boolean }) {
  if (!busy) return null;
  return (
    <div className="list-overlay" role="status" aria-live="polite">
      <span className="hs-spinner" aria-hidden="true" />
      <span>Fetching…</span>
    </div>
  );
}
// The by-ICP list filter above Step-1 and Step-2 (S19) — identical bar the title and the Step-1
// "pick an ICP" warn-highlight. Renders nothing when there's ≤1 ICP (nothing to filter by).
export function IcpFilterSelect({
  options,
  value,
  onChange,
  title,
  highlight,
}: {
  options: { id: string; label: string }[];
  value: string;
  onChange: (v: string) => void;
  title: string;
  highlight?: boolean;
}) {
  if (options.length <= 1) return null;
  return (
    <select
      className="select"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      title={title}
      style={
        highlight
          ? {
              borderColor: "var(--warn)",
              boxShadow: "0 0 0 3px var(--warn-wash)",
              transition: "box-shadow 0.2s",
            }
          : undefined
      }
    >
      <option value="">All ICPs</option>
      {options.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
// L20 (a11y) — Enter/Space activates a clickable non-button element (role="button"), matching a
// native button, so the expand/collapse rows are reachable without a mouse.
export const activateOnKey =
  (fn: () => void) => (e: { key: string; preventDefault: () => void }) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };

// Whole-row selection: like activateOnKey, but fires ONLY when the row itself is the focused element
// — a bubbled keydown from a focusable descendant (a link, or the Step-2 company cell that has its own
// Enter/Space collapse handler) is ignored, so one keypress never triggers two actions.
export const activateOnSelfKey =
  (fn: () => void) =>
  (e: {
    key: string;
    preventDefault: () => void;
    target: EventTarget;
    currentTarget: EventTarget;
  }) => {
    if (e.target !== e.currentTarget) return;
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      fn();
    }
  };

// A footnote bucket (low_fit / excluded_by_rules) is sub-grouped by WHY each row landed there, so
// the operator can scan the rejection reasons at a glance (spec §9). A gate-killed row carries a
// canonical reason string ("wrong vertical", "too large", "rule: B2B only", …); a low_fit row that
// was actually SCORED low (a real score_total, free-text reason) has no canonical tag, so all such
// rows fold into one "Low score" group instead of fragmenting into one-off reasons.
export function prettyReason(reason: string): string {
  const s = (reason || "")
    .trim()
    .replace(/^rule:\s*/i, "")
    .replace(/_/g, " ");
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : "";
}
export type SubGroup = { key: string; label: string; rows: CompanyApi[] };
export function subGroupsOf(rows: CompanyApi[]): SubGroup[] {
  const groups = new Map<string, SubGroup>();
  for (const c of rows) {
    const scoredLow = c.label === "low_fit" && c.score_total != null;
    const key = scoredLow ? "__scored_low" : (c.reason || "").trim().toLowerCase() || "__other";
    const label = scoredLow ? "Low score" : prettyReason(c.reason) || "Other";
    const g = groups.get(key);
    if (g) g.rows.push(c);
    else groups.set(key, { key, label, rows: [c] });
  }
  // Biggest group first — the most common rejection reason is what the operator most wants to see.
  return [...groups.values()].sort((a, b) => b.rows.length - a.rows.length);
}

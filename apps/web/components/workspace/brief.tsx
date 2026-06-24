"use client";
import { useState } from "react";
import clsx from "clsx";
import { type RowError } from "@/lib/csv";

// type-and-enter chips for multi-value fields
export function TagInput({
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
export function PillGroup({
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
export function Lbl({
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
export function ExclFormat() {
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

// Skipped-row report shown under an exclusion field after an import.
export function CsvErrors({ errors, onDismiss }: { errors?: RowError[]; onDismiss: () => void }) {
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
export function Section({
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

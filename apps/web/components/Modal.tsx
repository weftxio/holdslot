"use client";
import { useEffect, useRef } from "react";
import "./modal.css";

/**
 * Centered modal over a dimmed backdrop, built from the existing `.panel` / `.panel-head`
 * frame so it matches the design system. Closes on Esc, backdrop click, or the ✕ button;
 * locks body scroll and moves focus inside while open. Title/subtitle render via JSX (never
 * innerHTML). Honors prefers-reduced-motion via modal.css.
 */
export function Modal({
  open,
  onClose,
  title,
  subtitle,
  footer,
  children,
  className,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  subtitle?: string;
  footer?: React.ReactNode;
  children: React.ReactNode;
  className?: string;
}) {
  const dialogRef = useRef<HTMLDivElement>(null);
  // Keep the latest onClose without putting it in the effect deps — callers pass a fresh arrow
  // each render, so depending on it would re-run the effect (and steal focus to the ✕ button)
  // on every keystroke inside the modal, closing it when a space/Enter "clicks" that button.
  // Sync it in an effect (after commit), never by mutating the ref during render.
  const onCloseRef = useRef(onClose);
  useEffect(() => {
    onCloseRef.current = onClose;
  });

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onCloseRef.current();
    };
    document.addEventListener("keydown", onKey);
    const prevOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    dialogRef.current?.querySelector<HTMLElement>("input, textarea, button")?.focus();
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prevOverflow;
    };
  }, [open]);

  if (!open) return null;

  return (
    <div
      className="modal-overlay"
      onMouseDown={(e) => {
        if (e.target === e.currentTarget) onClose();
      }}
    >
      <div
        className={`modal-dialog panel${className ? ` ${className}` : ""}`}
        role="dialog"
        aria-modal="true"
        ref={dialogRef}
      >
        <div className="panel-head">
          <div>
            <h3>{title}</h3>
            {subtitle ? <div className="ph-sub">{subtitle}</div> : null}
          </div>
          <button className="modal-x" type="button" aria-label="Close" onClick={onClose}>
            ✕
          </button>
        </div>
        <div className="modal-body">{children}</div>
        {footer ? <div className="modal-foot">{footer}</div> : null}
      </div>
    </div>
  );
}

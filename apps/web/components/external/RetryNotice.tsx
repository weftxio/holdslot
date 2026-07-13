"use client";

/**
 * The transient-load affordance shared by the public-token pages (booking · approval · feedback).
 * These endpoints are never-404 — a genuinely dead link returns a 200 `state`, so a THROWN load
 * error is always transient (Aurora cold-start / network). Rather than fake an "expired" pane on a
 * hiccup (the M1/M5 bug), the page shows this retry block and keeps the link alive. Styles reuse the
 * external card's existing `.ph`/`.btn` classes — no new CSS.
 */
export function RetryNotice({ onRetry }: { onRetry: () => void }) {
  return (
    <div className="ph" style={{ padding: "24px 4px", textAlign: "center" }}>
      <p style={{ marginBottom: 14 }}>
        We couldn&apos;t load this just now — the server may be waking up. Your link is still valid.
      </p>
      <button className="btn btn-ghost" onClick={onRetry}>
        Try again
      </button>
    </div>
  );
}

// Console nav glyphs — Lucide icons (ISC-licensed), inlined so there's no runtime icon dependency.
// Each maps to what its section actually does; they carry the meaning when the sidebar collapses to
// an icon-only rail. Sized/coloured by the `.ico` CSS (stroke = currentColor, so they follow the
// link's colour and the active pill's ink). Paths are verbatim from lucide-static.
import type { ReactNode } from "react";

const glyph = (children: ReactNode) => (
  <svg
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    strokeWidth={2}
    strokeLinecap="round"
    strokeLinejoin="round"
    aria-hidden="true"
  >
    {children}
  </svg>
);

// Keys match the two Get-Meeting items plus the StatusTabKey values (approval/booking/feedback), so
// the sidebar can index straight off a status key.
export const NAV_ICONS: Record<string, ReactNode> = {
  // briefcase — the work hub
  workspace: glyph(
    <>
      <path d="M16 20V4a2 2 0 0 0-2-2h-4a2 2 0 0 0-2 2v16" />
      <rect width="20" height="14" x="2" y="6" rx="2" />
    </>,
  ),
  // bar chart — performance / funnel metrics
  performance: glyph(
    <>
      <path d="M3 3v16a2 2 0 0 0 2 2h16" />
      <path d="M18 17V9" />
      <path d="M13 17V5" />
      <path d="M8 17v-3" />
    </>,
  ),
  // clipboard-check — approve the prospect list
  approval: glyph(
    <>
      <rect width="8" height="4" x="8" y="2" rx="1" ry="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
      <path d="m9 14 2 2 4-4" />
    </>,
  ),
  // calendar-check — meetings getting booked
  booking: glyph(
    <>
      <path d="M8 2v4" />
      <path d="M16 2v4" />
      <rect width="18" height="18" x="3" y="4" rx="2" />
      <path d="M3 10h18" />
      <path d="m9 16 2 2 4-4" />
    </>,
  ),
  // message-square-text — post-meeting feedback
  feedback: glyph(
    <>
      <path d="M22 17a2 2 0 0 1-2 2H6.828a2 2 0 0 0-1.414.586l-2.202 2.202A.71.71 0 0 1 2 21.286V5a2 2 0 0 1 2-2h16a2 2 0 0 1 2 2z" />
      <path d="M7 11h10" />
      <path d="M7 15h6" />
      <path d="M7 7h8" />
    </>,
  ),
};

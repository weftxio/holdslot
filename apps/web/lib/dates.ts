// Shared date helpers. The Data API hands back our UTC timestamps as timezone-NAIVE ISO strings (no
// trailing Z / ±HH:MM), which `new Date(iso)` would parse as browser-LOCAL — showing the raw UTC
// digits and, in HK (UTC+8), pushing day-groups / "7-day" windows / times off by 8h. Pin them to UTC
// so `toLocale*` renders in the viewer's own zone. (R16 — one source of truth for the `whenLabel`
// that spec.tsx and FindHistoryDrawer both used, killing the R27 duplicate.)

// Parse an ISO instant, treating a timezone-naive value as UTC. Returns null when unusable.
export function parseUtc(iso: string | null | undefined): Date | null {
  if (!iso) return null;
  const hasTz = /[zZ]$/.test(iso) || /T.*[+-]\d{2}:?\d{2}$/.test(iso);
  const d = new Date(hasTz ? iso : iso + "Z");
  return Number.isNaN(d.getTime()) ? null : d;
}

// "Jul 9, 2:14 PM GMT+8" from an ISO instant, rendered in the VIEWER's own timezone; "" when unusable.
export function whenLabel(iso?: string | null): string {
  const d = parseUtc(iso);
  if (!d) return "";
  return d.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZoneName: "short",
  });
}

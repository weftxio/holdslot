// Multi-client helpers. Clients + selection persist in localStorage (ported from
// design/client-switch.js). The active client is the `[client]` URL slug.

export type Client = { name: string; slug: string };

export const DEFAULT_CLIENTS: Client[] = [
  // Single tenant for the initial build — we dogfood the product on our own tenant
  // (HoldSlot = tenant #0; see docs/initial-build-plan.md). The schema stays
  // multi-tenant, so adding a paying client later is one INSERT, not a redesign.
  { name: "HoldSlot", slug: "holdslot" },
];
export const DEFAULT_CLIENT_SLUG = DEFAULT_CLIENTS[0].slug;

// The page a user lands on after login / client switch / clicking the logo.
// Single source of truth so the default landing changes in one place.
export const DEFAULT_CLIENT_PAGE = "workspace";

const KEY = "holdslot_clients";

export function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

export function loadClients(): Client[] {
  if (typeof window === "undefined") return DEFAULT_CLIENTS;
  try {
    const list = JSON.parse(localStorage.getItem(KEY) || "null");
    if (Array.isArray(list)) {
      // N44 — keep only well-formed {name, slug} entries. A malformed stored value (hand-edited, or
      // an older/other shape) must not reach render, where a `.slug`/`.name` access would throw and
      // white-screen the whole console. Fall back to the defaults when nothing survives.
      const clean = list.filter(
        (c): c is Client =>
          !!c && typeof c.name === "string" && typeof c.slug === "string" && c.slug.length > 0,
      );
      if (clean.length) return clean;
    }
  } catch {
    /* ignore */
  }
  return DEFAULT_CLIENTS;
}

export function saveClients(list: Client[]) {
  if (typeof window === "undefined") return;
  try {
    localStorage.setItem(KEY, JSON.stringify(list));
  } catch {
    /* ignore */
  }
}

/** Adds a client (deduping the slug) and returns the created record. */
export function addClient(list: Client[], name: string): Client {
  let slug = slugify(name) || `client-${list.length + 1}`;
  const base = slug;
  let i = 2;
  while (list.some((c) => c.slug === slug)) slug = `${base}-${i++}`;
  return { name: name.trim(), slug };
}

/** Pure slug → title (server/client stable, used for the topbar crumb). */
export function slugToTitle(slug: string): string {
  return slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

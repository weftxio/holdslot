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

// §5 cleanup — the localStorage client list (loadClients/saveClients/addClient + its KEY) was
// removed with N45: the switcher now reads the caller's real memberships from /me, so a separate
// localStorage cache would only drift from the source of truth. `slugify` stays (slug preview).
export function slugify(s: string): string {
  return s
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

/** Pure slug → title (server/client stable, used for the topbar crumb). */
export function slugToTitle(slug: string): string {
  return slug
    .split("-")
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}

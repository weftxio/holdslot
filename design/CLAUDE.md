# HoldSlot · product mocks

High-fidelity HTML mocks for HoldSlot, a done-for-you B2B service that books qualified
sales meetings. Built from the approved marketing homepage as a locked style reference.

## Pages

| File | Purpose | Auth |
|---|---|---|
| `home.html` | Marketing homepage (hero, pinned "how it works" flow, pricing formula) | public |
| `login.html` | Operator sign-in + forgot-password flow | public |
| `overview.html` | Console dashboard: meetings-booked headline, needs-attention, leads funnel | logged-in |
| `workspace.html` | Console workspace: Business brief / ICPs / Prospect list / Sendout Batch / Campaign / Reply queue / Billing / Meeting summaries | logged-in |
| `external-status.html` | "Client Action Status": sendout templates + status logs for approval / booking / feedback | logged-in |
| `client-approval.html` | Client-facing one-click prospect-list approval | email link |
| `booking.html` | Prospect-facing slot picker + recording consent | email link |
| `feedback.html` | Prospect-facing post-meeting rating + comment | email link |

External-facing pages each have a valid and an expired state (toggle top-right, or `?state=expired`).

## Shared assets

- `holdslot.css`: the design system. All console + external pages link it. Tokens, buttons,
  badges, tables, tabs, the console shell (sidebar + topbar), forms, toasts, and the
  external-page card live here. **Change brand values here.**
- `client-switch.js`: the sidebar client switcher (select client, create new client → URL slug).
  Persists clients + selection in `localStorage`; updates any `[data-client-name]` element.

`home.html` is intentionally self-contained (its own `<style>`) so the landing page works
standalone; its tokens mirror `holdslot.css`.

## Design system

- **Accent:** Cerulean `#9BB7D6`; darker `#5E7C9E` for contrast; light `#EEF3F9` surfaces;
  near-black `#0E1116` text on white. Status colors are low-chroma (see `:root`).
- **Type:** Fraunces (display) + Archivo (body), via Google Fonts.
- **Separators:** middot `·` only; no em/en dashes anywhere in copy.
- **Tone:** minimal, trustable, result-oriented.

## Conventions

- All sample data is marked with a `.sample` chip or sits behind a dashed `.ph` placeholder.
  Replace these with real data/wiring when productionising.
- Console pages share an identical sidebar shell; keep them in sync when editing nav.
- Interactions are mocked client-side (no backend): tab switching, reply approve/edit,
  batch creation feeding the Sendout Batch tab, the pricing-formula visuals, etc.
- Canonical HTML (explicit closing tags, quoted attributes) for clean diffing/editing.

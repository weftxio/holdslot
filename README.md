# HoldSlot

Done-for-you B2B service that turns a client brief into qualified, booked sales meetings, and
bills only for meetings that qualify. Multi-client.

## Repo layout

```
apps/
  web/        Next.js (App Router, TS) — the product UI. First development item: mock UI.
  api/        FastAPI backend — placeholder (built later).
infra/        migrations / deploy config — placeholder (built later).
design/       Vendored Claude Design bundle (read-only reference). Mocks govern UI exactly.
```

`design/` is the source of truth for the UI. See `design/CLAUDE.md` for the page list and the
design system; `design/holdslot.css` for tokens/components; `design/chats/` for design intent.

## Develop

Requires Node + pnpm.

```
pnpm install
pnpm dev        # runs apps/web (Next.js)
```

## Status

Phase 1 — building the mock UI in `apps/web`, ported pixel-faithfully from `design/`, backed by
mock fixtures (no backend). The backend (`apps/api`) and `infra/` follow later.

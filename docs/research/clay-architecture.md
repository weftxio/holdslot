# Clay architecture research (2026-06-19)

Evidence behind the Phase C "one stateless table" design in
[`../initial-build-plan.md`](../initial-build-plan.md) + [`../data-schema.md`](../data-schema.md).

## Key findings

1. **No table-creation API on any tier.** No REST endpoint, no Zapier/Make "create table" action (only
   "create record" = push rows), no programmatic "Share as Template" / duplicate. Confirmed by probing
   the live key (2026-06-14: management endpoints reject it as non-admin) and by Clay docs/community.
   The stored `holdslot/prod/clay` `api_key` is a **webhook auth token** (`x-clay-webhook-auth`), not a
   REST key. → Automating per-client table creation is not viable (only brittle browser automation).
2. **The correct pattern is ONE shared table, not one per client.** Agencies run **80+ clients from a
   single table/workspace** (ColdIQ); Clay's own credit guidance is "one master table, slice with
   filters/views." Per-client tables are an explicit anti-pattern (structure-sync across N tables). →
   Tenant and industry are **columns/attributes, never table boundaries.**
3. **Clay = stateless enrichment compute, not storage.** Push rows in (webhook) → enrich → pull out →
   clear. Our DB is the only system of record; tenant/dedup/suppression/fit/lineage live there.
4. **Webhook cap = 50k submissions per webhook, lifetime, non-resettable.** But you add a **new webhook
   to the same table** when one fills (multiple webhooks/table OK). Rotation is the only recurring manual
   op — rare, volume-driven.
5. **Row caps:** Free 200/table, Launch & Growth 50k/table; **Enterprise auto-delete (passthrough)** =
   unlimited throughput (triggers at a 5k-row threshold, sends to a destination, then deletes).
6. **Tables per workspace = unlimited on every tier.** Table *count* is never the constraint; credits +
   rows-per-table + manual creation labour are.
7. **Credits charged per row per enrichment action.** Reuse is free via **Lookup columns** (pull from
   another table/CRM at 0 credits) and **"only run if [field] empty"** (skipped step = no Action, no
   credit). **Auto-dedupe** on a column (domain/email) prevents duplicate enrichment. → Dedup *before*
   push against our identity cache so a prospect wanted by N clients is enriched once, paid once.
8. **Automated results-OUT is Growth-gated.** HTTP API column / send-to-webhook require Growth+; Free &
   **Launch use manual CSV export**. (Webhook-triggered tables can't respond to the inbound request.)

## Pricing / limits (clay.com/pricing, 2026)

| Tier | Price/mo | Tables | Rows/table | Data Credits/mo | Actions/mo | Results OUT |
|---|---|---|---|---|---|---|
| Free | $0 | unlimited | 200 | 100 | 500 | CSV only |
| Launch | ~$167–185 | unlimited | 50,000 | 2,500 | 15,000 | CSV only |
| Growth | ~$446–495 | unlimited | 50,000 | 6,000 | 40,000 | + HTTP API column / webhook |
| Enterprise | custom | unlimited | 50,000 (+auto-delete) | 100,000+ | 200,000+ | + passthrough auto-delete |

Pricing = Data Credits (~$0.05) + Actions (<$0.01); failed lookups no longer cost credits (re-priced 2026-03-11).

## Sources
- [Clay Pricing](https://www.clay.com/pricing) · [Plans & billing](https://university.clay.com/docs/plans-and-billing)
- [Best practices for multiple clients — Community](https://community.clay.com/x/general/ue1m1o1nva90/best-practices-for-setting-up-clay-accounts-when-m) · [ColdIQ "80 clients from one table"](https://x.com/itsalexvacca/status/2039658156645884033) · [ColdIQ partner](https://www.clay.com/experts/partner/coldiq)
- [Webhook limits — Community](https://community.clay.com/x/bugs/y0fw8pbzkzgq/limitations-on-webhook-calls-to-clay-tables-explai) · [Auto-delete docs](https://university.clay.com/docs/auto-delete) · [Webhook integration guide](https://university.clay.com/docs/webhook-integration-guide)
- [Credit conservation](https://university.clay.com/docs/clay-credit-conservation) · [Auto-dedupe changelog](https://www.clay.com/changelog/auto-dedupe) · [Table management settings](https://university.clay.com/docs/table-management-settings)
- [HTTP API integration](https://university.clay.com/docs/http-api-integration-overview) · [Does Clay have an API?](https://university.clay.com/docs/using-clay-as-an-api) · [Workbook/table sharing](https://university.clay.com/docs/workbook-table-sharing-guide)

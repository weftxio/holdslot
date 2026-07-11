# Production cutover register (G7)

The final-fix-plan (G1–G6) is complete. A set of findings were **deliberately deferred to the prod
cutover** rather than applied on the shared dev-tier backend now — mostly because they add or tighten
AWS resources (Q6: zero new AWS resources / no tightening until cutover) and would risk the running
dev Lambda. This is the running list to work through when standing up the production workspace.

## Deferred findings (each has an in-code cutover note pointing here)

| # | Where | Do at cutover |
|---|---|---|
| N20 | `infra/terraform/lambda.tf` (`api_async`) | Add `destination_config { on_failure { destination = <SQS/SNS ARN> } }` + a CloudWatch alarm on `AsyncEventsDropped` + `DestinationDeliveryFailures`, so a silently dropped background job is paged, not just surfaced by a user re-poll. |
| N52 | `infra/terraform/iam.tf` (`lambda_secrets`) | Replace the `${secrets_prefix}/*` wildcard with the exact secret ARNs the app reads (`.../app`, `.../openrouter`, `.../apollo`). Verify the live Lambda still starts (it must read exactly those). |
| N54 | `infra/terraform/apigw.tf` (`default` stage) | Add `default_route_settings { throttling_burst_limit, throttling_rate_limit }` sized to expected load, so the gateway sheds excess instead of amplifying it into Lambda concurrency + spend. |

## Other cutover hardening (from the plan's G7 register)

- **N3 (already applied dev)** — Aurora now has `deletion_protection = true` + a `final_snapshot_identifier`. Confirm it survives the prod-workspace apply; to intentionally destroy, flip deletion_protection off in a separate apply first.
- **N53 (done)** — `amplify.yml` preBuild fails when `NEXT_PUBLIC_API_BASE_URL` is unset. Confirm the prod Amplify branch sets it to the real API base.
- **e2e in CI** — wire `pnpm exec playwright test` into the deploy pipeline as a blocking gate (it is currently a manual pre-push gate, Q8). Baseline is 18/18 green.
- **Aurora min-ACU** — revisit `var.aurora_min_acu` (scale-to-zero is a dev cost choice; prod may want a warm floor to avoid the "Resuming" first-call latency).
- **S3 public-access-block** — confirm PAB on any bucket introduced at cutover (none today).
- **Fresh JWT signing keys** — mint prod-only `jwt_signing_key` / `jwt_refresh_key` secrets (never reuse dev keys).
- **HOLDSLOT_SEED_PASSWORD** — needed only to bootstrap a fresh DB (migration 0002); see `infra/README.md` (N50).

## Deploy runbook (recap)

Backend before frontend. **Migration order depends on the change** (see `[[deploy-process]]` memory):
expand → `alembic upgrade` then deploy; contract OR add-a-constraint-old-code-violates → deploy the
Lambda first, then `alembic upgrade`. Push #1 of this plan applied `0027` (a constraint add) with the
**deploy-first** order for exactly that reason. Push #2 (G5–G6) adds **no migration**.

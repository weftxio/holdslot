# apps/api/scripts

Operational scripts for the HoldSlot backend.

## build-and-deploy.sh — ship the API Lambda

Builds the Linux x86_64 artifact (uv wheels + `app/`), publishes a new Lambda
version, waits for SnapStart to finish, then shifts the `live` alias.

```bash
AWS_PROFILE=holdslot ./apps/api/scripts/build-and-deploy.sh
```

- **Target:** the single `holdslot-dev-api` Lambda (alias `live`), which serves
  **both** the dev and prod frontends at `https://api.tryholdslot.com`. There is
  no separate prod backend — deploying this Lambda updates the API for everyone.
- **Permissions:** the `claude_code` identity already has `AWSLambda_FullAccess`,
  so it can run this. (`claude_code` is read-only **only** for Terraform/infra
  provisioning and writing prod secrets — those stay founder-only. Operational
  deploys — Lambda code, Data API migrations, Amplify — are allowed.)
- **Migrations first.** If a migration is pending, run `alembic upgrade head`
  (see [`infra/README.md`](../../../infra/README.md) → *Operational deploy*)
  **before** this script. A schema-breaking migration (e.g. a stage rename) and
  its matching Lambda code must ship back-to-back, migration first.
- **Verify:** `curl -fsS https://api.tryholdslot.com/health` and
  `python3 apps/api/scripts/verify_keys.py`.

## verify_keys.py

Connection test for the platform secrets in AWS Secrets Manager
(`holdslot/prod/{app,openrouter,apollo,smartlead,google}`). Runs the minimal
read/auth call each build-plan phase needs and prints a `PASS`/`FAIL`/`PEND`
table — nothing out of scope.

It is **phase-aware**: fields a later phase provisions (Smartlead's sending
accounts + webhook secret at Phase E; Google's delegation at Phase F) report as
`PEND` ("pending"), not `FAIL`, so a clean run today exits 0. Pass `--strict` to
treat `PEND` as failure once you reach the phase that needs the field. The Apollo
`key` is reported as **stored** (not API-validated — company search would cost a
plan credit), so the whole run stays free.

`app` is first-party (HoldSlot's own JWT signing/refresh keys), so its check is
offline: presence, strength, and distinctness. The Aurora master credential is a
separate RDS-managed secret, tested later.

**Stdlib only** — no pip install. Uses the `aws` CLI for secret reads, `urllib`
for HTTP, and `openssl` to sign the Google delegated JWT. Secret values are never
printed.

```bash
# all free checks (PEND for future-phase fields, exit 0)
python3 apps/api/scripts/verify_keys.py

# at a later phase: require the phase's fields to be present (PEND → fail)
python3 apps/api/scripts/verify_keys.py --strict

# one platform only
python3 apps/api/scripts/verify_keys.py --only google
```

Defaults to `--profile holdslot --region us-east-1` (override with flags or
`AWS_PROFILE`/`AWS_REGION`). The caller's IAM identity needs
`secretsmanager:GetSecretValue` on the `holdslot/prod/*` secrets.

Cost: every check is free — no API calls that consume credits (Apollo is attested
as stored, not exercised).

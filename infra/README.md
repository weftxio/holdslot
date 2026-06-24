# infra — HoldSlot infrastructure

Terraform (IaC) + Alembic (schema source of truth) for the backend. See Phase A in
[`docs/initial-build-plan.md`](../docs/initial-build-plan.md).

```
terraform/   AWS resources (Aurora SLv2 + Data API, Lambda+SnapStart, API GW, IAM, SES, budget)
  scripts/bootstrap-state.sh   one-time: create the S3 state bucket before first init
alembic/     migrations (models + baseline + seed land in A3)
```

## Design choices (simple now, scalable later)
- **Aurora Serverless v2 + RDS Data API** — Lambda reaches the DB over the Data API
  (HTTPS), so it stays **out of the VPC** (no NAT). `min_capacity = 0` → scale-to-zero.
- **S3-native state locking** (`use_lockfile`) — no DynamoDB lock table.
- **Workspace-parameterised env** — the default workspace is `dev`; production is a later
  `terraform workspace new prod`, not a rewrite.
- **Terraform owns infra; CI owns code** — the Lambda's code attributes are under
  `ignore_changes`, so `aws lambda update-function-code` (A5) doesn't fight Terraform.

## Apply (Phase A — A2)
> Provisions billable AWS resources. Run with credentials that can write to account
> `138743894336` (the `claude_code` identity is read-only and cannot do this).

```bash
cd infra/terraform
AWS_PROFILE=holdslot ./scripts/bootstrap-state.sh   # one-time: state bucket
AWS_PROFILE=holdslot terraform init
AWS_PROFILE=holdslot terraform plan                 # review
AWS_PROFILE=holdslot terraform apply                # creates the stack
```
Outputs include `api_base_url` (→ `apps/web` `API_BASE_URL`, A5), the Aurora cluster +
master-secret ARNs (Data API + connection test), and `ses_dkim_tokens` (add as DNS CNAMEs).

## Operational deploy (code & schema — NOT infra)

> Provisioning infra (`terraform apply`) and writing prod secrets are **founder-only**
> (read-only there). **Operational deploys below are allowed for `claude_code`** — it has
> `AWSLambda_FullAccess`, `AmazonRDSFullAccess`, `AdministratorAccess-Amplify`, `rds-data`
> on the cluster, and `GetSecretValue` on `holdslot/prod/*` + the `rds!*` master secret.

**Topology (one shared backend).** A single Lambda `holdslot-dev-api` (alias `live`) sits
behind `https://api.tryholdslot.com` and serves **both** frontends. The web app is an
Amplify monorepo app (`apps/web`): branch `dev` → DEVELOPMENT, branch `main` → PRODUCTION,
**both `autoBuild=true`** and both pointed at the same `NEXT_PUBLIC_API_BASE_URL`. So:
pushing `dev` auto-deploys the dev site; merging `dev`→`main` auto-deploys the prod site.
There is no manual frontend deploy step and no separate prod backend.

**Order: backend before frontend.** The frontend and backend ship as a pair — deploy the
API, *then* let Amplify build the site, so the new UI never calls a stale API.

```bash
# 0. env for Data API migrations (ARNs are stable; master secret via describe-db-clusters)
export AWS_PROFILE=holdslot AWS_REGION=us-east-1 HOLDSLOT_DB_NAME=holdslot
export HOLDSLOT_DB_CLUSTER_ARN=arn:aws:rds:us-east-1:138743894336:cluster:holdslot-dev-aurora
export HOLDSLOT_DB_SECRET_ARN=$(aws rds describe-db-clusters \
  --query 'DBClusters[0].MasterUserSecret.SecretArn' --output text)

# 1. migrate (Aurora is scale-to-zero — the first call may say "Resuming"; just retry)
apps/api/.venv/bin/alembic -c infra/alembic/alembic.ini current   # check
apps/api/.venv/bin/alembic -c infra/alembic/alembic.ini upgrade head

# 2. deploy the Lambda (build → publish → SnapStart → shift `live` alias)
AWS_PROFILE=holdslot ./apps/api/scripts/build-and-deploy.sh

# 3. verify, then ship the frontend
curl -fsS https://api.tryholdslot.com/health
git push origin dev            # → dev site builds
# git checkout main && git merge --ff-only dev && git push origin main   # → prod site builds
```

A **schema-breaking** migration (e.g. the 0013 `fit_scoring`→`company_fit` rename) breaks
the live Lambda the instant it runs, so run step 1 and step 2 back-to-back. Additive
migrations are safe to run ahead of the code.

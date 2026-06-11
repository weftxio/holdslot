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

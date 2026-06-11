#!/usr/bin/env bash
# Source this to run the API locally against the dev Aurora (Data API) with your AWS creds.
#   source scripts/dev-env.sh && uvicorn app.main:app --reload
export AWS_PROFILE=${AWS_PROFILE:-holdslot}
export AWS_REGION=${AWS_REGION:-us-east-1}
export HOLDSLOT_ENV=dev
export HOLDSLOT_DB_NAME=holdslot
export HOLDSLOT_SECRETS_PREFIX=holdslot/prod
TF=${TERRAFORM:-terraform}   # override with TERRAFORM=/path/to/terraform if not on PATH
export HOLDSLOT_DB_CLUSTER_ARN=$("$TF" -chdir="$(git rev-parse --show-toplevel)/infra/terraform" output -raw aurora_cluster_arn 2>/dev/null || echo "$HOLDSLOT_DB_CLUSTER_ARN")
export HOLDSLOT_DB_SECRET_ARN=$("$TF" -chdir="$(git rev-parse --show-toplevel)/infra/terraform" output -raw aurora_master_secret_arn 2>/dev/null || echo "$HOLDSLOT_DB_SECRET_ARN")

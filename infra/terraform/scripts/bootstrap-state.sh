#!/usr/bin/env bash
# One-time: create the S3 bucket that holds Terraform remote state, BEFORE the first
# `terraform init`. State can't bootstrap its own backend, so this runs out-of-band.
# Idempotent — safe to re-run. Uses S3-native locking (no DynamoDB table needed).
#
# Usage:  AWS_PROFILE=holdslot ./bootstrap-state.sh
set -euo pipefail

BUCKET="holdslot-tfstate-138743894336"
REGION="us-east-1"

echo "Ensuring state bucket s3://${BUCKET} (${REGION})..."
if aws s3api head-bucket --bucket "${BUCKET}" 2>/dev/null; then
  echo "  bucket exists."
else
  # us-east-1 must NOT pass a LocationConstraint.
  aws s3api create-bucket --bucket "${BUCKET}" --region "${REGION}"
  echo "  created."
fi

aws s3api put-bucket-versioning \
  --bucket "${BUCKET}" \
  --versioning-configuration Status=Enabled

aws s3api put-bucket-encryption \
  --bucket "${BUCKET}" \
  --server-side-encryption-configuration \
  '{"Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"aws:kms"}}]}'

aws s3api put-public-access-block \
  --bucket "${BUCKET}" \
  --public-access-block-configuration \
  BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

echo "Done. Now: terraform init"

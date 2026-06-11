#!/usr/bin/env bash
# Build the Lambda artifact (Linux x86_64 wheels) and deploy it: update code, publish a
# version, wait for SnapStart to finish optimizing, then shift the `live` alias.
#
# Usage:  AWS_PROFILE=holdslot ./scripts/build-and-deploy.sh
set -euo pipefail

FN=${LAMBDA_FN:-holdslot-dev-api}
REGION=${AWS_REGION:-us-east-1}
HERE="$(cd "$(dirname "$0")/.." && pwd)"   # apps/api
cd "$HERE"

echo "==> Building Linux x86_64 package"
rm -rf build/pkg build/holdslot-api.zip
mkdir -p build/pkg
uv pip install --python-platform x86_64-manylinux2014 --python-version 3.12 \
  --target build/pkg --only-binary=:all: \
  fastapi mangum "sqlalchemy>=2.0" sqlalchemy-aurora-data-api argon2-cffi pyjwt email-validator

# boto3/botocore ship in the Lambda runtime — drop them to shrink the artifact.
rm -rf build/pkg/boto3* build/pkg/botocore* build/pkg/s3transfer*
find build/pkg -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

cp -r app build/pkg/app
(cd build/pkg && zip -qr ../holdslot-api.zip . -x "*.pyc")
echo "    artifact: $(du -h build/holdslot-api.zip | cut -f1)"

echo "==> Updating function code + publishing version"
VER=$(aws lambda update-function-code --function-name "$FN" \
  --zip-file fileb://build/holdslot-api.zip --publish \
  --region "$REGION" --query Version --output text)
echo "    published version $VER"

echo "==> Waiting for version $VER to be Active (SnapStart)"
for _ in $(seq 1 40); do
  ST=$(aws lambda get-function-configuration --function-name "$FN" --qualifier "$VER" \
    --region "$REGION" --query State --output text)
  [ "$ST" = "Active" ] && break || sleep 10
done

echo "==> Shifting live alias -> $VER"
aws lambda update-alias --function-name "$FN" --name live --function-version "$VER" \
  --region "$REGION" --query '[Name,FunctionVersion]' --output text

echo "==> Smoke test"
BASE=$("${TERRAFORM:-terraform}" -chdir="$HERE/../../infra/terraform" output -raw api_base_url 2>/dev/null || true)
[ -n "${BASE:-}" ] && curl -fsS -m 30 "$BASE/health" && echo " OK" || echo "set BASE manually to smoke test"

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
# N22 — resolve the runtime deps from pyproject.toml (the single source of truth) instead of a
# hardcoded list that silently drifts: a dependency added to the app but not mirrored here would only
# surface as an ImportError AFTER update-function-code + the alias shift, i.e. in production. `uv pip
# compile` pins the full tree for the Lambda target (Linux/3.12) — reproducible, and uv-native so it
# needs no particular system `python3`. boto3/botocore land here transitively but are stripped below.
# --only-binary=:all: at COMPILE time mirrors the --only-binary=:all: install below exactly: the
# resolver may only pin versions that have a usable wheel for the target platform. (Plain --no-build
# is weaker — it just forbids *building* sdists, so it can still pin a wheel-less version whose
# metadata came from an sdist, which the install then rejects.) Concretely: the latest
# argon2-cffi-bindings ships no manylinux2014 wheel, so this backtracks it to a version that does —
# and compile/install now share one constraint, so they can never diverge on any future dep.
uv pip compile pyproject.toml --quiet \
  --python-platform x86_64-manylinux2014 --python-version 3.12 --only-binary=:all: \
  -o build/requirements.txt
uv pip install --python-platform x86_64-manylinux2014 --python-version 3.12 \
  --target build/pkg --only-binary=:all: \
  -r build/requirements.txt

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
ACTIVE=""
for _ in $(seq 1 40); do
  ST=$(aws lambda get-function-configuration --function-name "$FN" --qualifier "$VER" \
    --region "$REGION" --query State --output text)
  if [ "$ST" = "Active" ]; then ACTIVE=1; break; fi
  sleep 10
done
# N55 — never shift the live alias onto a version that isn't Active. The loop used to fall through on
# timeout and point `live` at a still-optimizing/failed version, breaking prod on the next cold start.
if [ -z "$ACTIVE" ]; then
  echo "!! version $VER never reached Active (last state: ${ST:-unknown}) — NOT shifting live" >&2
  exit 1
fi

echo "==> Shifting live alias -> $VER"
aws lambda update-alias --function-name "$FN" --name live --function-version "$VER" \
  --region "$REGION" --query '[Name,FunctionVersion]' --output text

echo "==> Smoke test"
BASE=$("${TERRAFORM:-terraform}" -chdir="$HERE/../../infra/terraform" output -raw api_base_url 2>/dev/null || true)
[ -n "${BASE:-}" ] && curl -fsS -m 30 "$BASE/health" && echo " OK" || echo "set BASE manually to smoke test"

# N56 — prune stale published versions. SnapStart bills a snapshot-cache fee
# (Lambda-SnapStart-Cached-GB-S) continuously for EVERY retained published version, not
# just the one `live` serves. Left unpruned it compounds ~$2/mo per deploy — 93 stale
# versions were ~$180/mo of pure cache in Jul 2026 (the whole account's cost spike). Keep
# only what rollback needs: the live target + the 3 newest. Housekeeping only — it runs
# LAST (alias shift + smoke test already succeeded above) and never aborts the deploy.
echo "==> Pruning old published versions (keep live target + 3 newest)"
KEEP_TARGET=$(aws lambda get-alias --function-name "$FN" --name live \
  --region "$REGION" --query FunctionVersion --output text)
ALL_VERS=$(aws lambda list-versions-by-function --function-name "$FN" --region "$REGION" \
  --query 'Versions[?Version!=`$LATEST`].Version' --output text | tr '\t' '\n' | sort -rn)
KEEP=$(printf '%s\n%s\n' "$KEEP_TARGET" "$(printf '%s\n' "$ALL_VERS" | awk 'NR<=3')" | sort -un)
for v in $ALL_VERS; do
  printf '%s\n' "$KEEP" | grep -qx "$v" && continue
  aws lambda delete-function --function-name "$FN" --qualifier "$v" --region "$REGION" \
    >/dev/null 2>&1 && echo "    pruned version $v" || echo "    !! prune failed for v$v (skipped)" >&2
done
echo "    kept versions: $(printf '%s ' $KEEP)"

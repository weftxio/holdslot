#!/usr/bin/env bash
# C0 smoke test pt2 — broad people search (no org scope) to capture a real row + chain people/match.
set -uo pipefail
cd "$(dirname "$0")"
KEY=$(AWS_PROFILE=holdslot aws secretsmanager get-secret-value \
  --secret-id holdslot/prod/apollo --query SecretString --output text | jq -r .key)
[ -z "$KEY" ] && { echo FATAL; exit 1; }
H_KEY="X-Api-Key: $KEY"; CT="Content-Type: application/json"; ACC="Accept: application/json"
BASE="https://api.apollo.io/api/v1"

echo "=== company row shape (from organizations[]) ==="
jq -c '(.organizations//[])[0] | {id, name, has_website:(has("website_url")), industry, n_employees:.estimated_num_employees, raw_address, street_address:(has("street_address")), postal_code:(has("postal_code"))}' companies_search.json

echo
echo "================ people search — broad (no org scope) ================"
code=$(curl -s -o people_search.json -D people_search.headers -w "%{http_code}" \
  -X POST "$BASE/mixed_people/api_search" -H "$H_KEY" -H "$CT" -H "$ACC" \
  -d '{"person_titles":["Sales Manager"],"include_similar_titles":true,"person_seniorities":["manager"],"page":1,"per_page":1}')
echo "HTTP $code"
echo "-- total_entries --"; jq -c '.total_entries' people_search.json
echo "-- person[0] field presence --"
jq -c '(.people//[])[0] | {id, first_name, has_last_name:has("last_name"), last_name, has_linkedin:has("linkedin_url"), linkedin_url, has_departments:has("departments"), departments, title, has_email:has("email"), email, org_id:.organization_id}' people_search.json
PERSON_ID=$(jq -r '(.people//[])[0].id // empty' people_search.json)
echo "-- person id: ${PERSON_ID:-<none>}"

echo
echo "================ people/match (enrich — 1 credit) ================"
if [ -n "$PERSON_ID" ]; then
  code=$(curl -s -o people_match.json -D people_match.headers -w "%{http_code}" \
    -X POST "$BASE/people/match" -H "$H_KEY" -H "$CT" -H "$ACC" \
    -d "$(jq -nc --arg id "$PERSON_ID" '{id:$id, reveal_personal_emails:true, reveal_phone_number:false}')")
  echo "HTTP $code"
  echo "-- credit headers --"; grep -iE 'x-(.*credit.*|.*usage.*|rate.*)' people_match.headers || true
  echo "-- enrich shape --"
  jq -c '.person | {email, email_status, has_phone:(has("phone_numbers")), n_phones:((.phone_numbers//[])|length), n_personal_emails:((.personal_emails//[])|length)}' people_match.json
else echo "SKIP no id"; fi
echo "=== files ==="; ls -la *.json

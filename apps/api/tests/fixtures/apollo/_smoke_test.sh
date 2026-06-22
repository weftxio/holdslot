#!/usr/bin/env bash
# C0 smoke test — Apollo Professional master key. Hits the 3 live endpoints at per_page:1,
# saves response bodies + headers as fixtures, prints only HTTP status + safe summaries.
# The key is read into a runtime var and used in headers only — never printed.
set -uo pipefail
cd "$(dirname "$0")"

KEY=$(AWS_PROFILE=holdslot aws secretsmanager get-secret-value \
  --secret-id holdslot/prod/apollo --query SecretString --output text | jq -r .key)
if [ -z "$KEY" ] || [ "$KEY" = "null" ]; then echo "FATAL: no key"; exit 1; fi
echo "key loaded (len=${#KEY})"
H_KEY="X-Api-Key: $KEY"
CT="Content-Type: application/json"
ACC="Accept: application/json"
BASE="https://api.apollo.io/api/v1"

echo
echo "================ 1) mixed_companies/search (credit-consuming) ================"
code=$(curl -s -o companies_search.json -D companies_search.headers \
  -w "%{http_code}" -X POST "$BASE/mixed_companies/search" \
  -H "$H_KEY" -H "$CT" -H "$ACC" \
  -d '{"q_organization_keyword_tags":["software"],"organization_num_employees_ranges":["11,50"],"page":1,"per_page":1}')
echo "HTTP $code"
echo "-- credit/rate headers --"; grep -iE 'x-(.*credit.*|.*minute.*|.*hour.*|.*day.*|rate.*)' companies_search.headers || true
echo "-- top-level keys --"; jq -r 'keys[]?' companies_search.json 2>/dev/null | tr '\n' ' '; echo
echo "-- pagination --"; jq -c '.pagination? // empty' companies_search.json 2>/dev/null
ORG_ID=$(jq -r '(.organizations // .accounts // [])[0].id // empty' companies_search.json 2>/dev/null)
echo "-- first org id: ${ORG_ID:-<none>}"

echo
echo "================ 2) mixed_people/api_search (0 credits, master key) ================"
PEOPLE_BODY=$(jq -nc --arg oid "$ORG_ID" '
  {person_titles:["Head of Sales","VP Sales"],
   include_similar_titles:true,
   person_seniorities:["head","vp"],
   page:1, per_page:1}
  + (if $oid != "" then {organization_ids:[$oid]} else {} end)')
code=$(curl -s -o people_search.json -D people_search.headers \
  -w "%{http_code}" -X POST "$BASE/mixed_people/api_search" \
  -H "$H_KEY" -H "$CT" -H "$ACC" -d "$PEOPLE_BODY")
echo "HTTP $code"
echo "-- credit/rate headers --"; grep -iE 'x-(.*credit.*|.*minute.*|.*hour.*|.*day.*|rate.*)' people_search.headers || true
echo "-- top-level keys --"; jq -r 'keys[]?' people_search.json 2>/dev/null | tr '\n' ' '; echo
echo "-- ambiguous-key check on people[0] (last_name / linkedin_url / departments) --"
jq -c '(.people // [])[0] | {has_last_name:(has("last_name")), last_name, has_linkedin:(has("linkedin_url")), linkedin_url, has_departments:(has("departments")), departments}' people_search.json 2>/dev/null
PERSON_ID=$(jq -r '(.people // [])[0].id // empty' people_search.json 2>/dev/null)
echo "-- first person id: ${PERSON_ID:-<none>}"

echo
echo "================ 3) people/match (enrich — 1 credit, reveal email) ================"
if [ -z "$PERSON_ID" ]; then
  echo "SKIP: no person id from search to match"
else
  code=$(curl -s -o people_match.json -D people_match.headers \
    -w "%{http_code}" -X POST "$BASE/people/match" \
    -H "$H_KEY" -H "$CT" -H "$ACC" \
    -d "$(jq -nc --arg id "$PERSON_ID" '{id:$id, reveal_personal_emails:true, reveal_phone_number:false}')")
  echo "HTTP $code"
  echo "-- credit/rate headers --"; grep -iE 'x-(.*credit.*|.*minute.*|.*hour.*|.*day.*|rate.*)' people_match.headers || true
  echo "-- enrich field shape --"
  jq -c '.person | {email, email_status, has_phone_numbers:(has("phone_numbers")), n_phones:((.phone_numbers//[])|length)}' people_match.json 2>/dev/null
fi

echo
echo "================ DONE — fixtures written ================"
ls -la *.json

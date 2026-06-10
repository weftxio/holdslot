# apps/api/scripts

Operational scripts for the HoldSlot backend. No app code yet — these run standalone.

## verify_keys.py

Connection test for the platform secrets in AWS Secrets Manager
(`holdslot/prod/{app,openrouter,clay,smartlead,google}`). Runs the minimal
read/auth call each build-plan phase needs and prints a `PASS`/`FAIL`/`PEND`
table — nothing out of scope.

It is **phase-aware**: fields a later phase provisions (Clay's table + webhook at
Phase C; Smartlead's sending accounts + webhook secret at Phase E) report as
`PEND` ("pending"), not `FAIL`, so a clean run today exits 0. Pass `--strict` to
treat `PEND` as failure once you reach the phase that needs the field. The Clay
`api_key` is reported as **stored** (not API-validated — that would cost a credit).

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

# also push one Clay test row (~1 credit) — delete the row afterwards
python3 apps/api/scripts/verify_keys.py --clay-push

# one platform only
python3 apps/api/scripts/verify_keys.py --only google
```

Defaults to `--profile holdslot --region us-east-1` (override with flags or
`AWS_PROFILE`/`AWS_REGION`). The caller's IAM identity needs
`secretsmanager:GetSecretValue` on the `holdslot/prod/*` secrets.

Cost: every check is free **except** the Clay `--clay-push` row (~1 credit). After
a push, delete the `HoldSlot Verify` row from the Clay table.

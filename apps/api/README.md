# apps/api — HoldSlot backend

FastAPI service, deployed to **AWS Lambda** behind **API Gateway (HTTP API) + SnapStart**
(Mangum adapter). One modular deployable; split only if scale ever demands it. Managed
outside the pnpm JS workspace.

Build order is in [`docs/initial-build-plan.md`](../../docs/initial-build-plan.md) (Phase A)
and the locked spec [`docs/backend-development-plan.md`](../../docs/backend-development-plan.md).

## Status — Phase A (S0) built & deployed (dev)
- **A1–A6 done.** Auth + clients API + central tenant×role guard live on Lambda; schema +
  seed on Aurora; both founders log in; multi-tenant scoping verified.
- **Live API:** `https://api.tryholdslot.com` (also `https://ooqe40p813.execute-api.us-east-1.amazonaws.com`).

## Layout
```
app/
  main.py          FastAPI app + Mangum handler; /health, CORS, routers
  core/            db (Data API engine), config (Secrets Manager), security (argon2+JWT),
                   deps (session + central access guard), email (SES)
  domains/
    auth/          login / refresh / forgot / reset  (router · service · schemas)
    clients/       /me, /clients, /{client}/context  (router · schemas)
  models.py        ORM models — identity + tenancy core (schema source of truth)
tests/             pytest (unit: no AWS; acceptance: live Aurora, auto-skipped without env)
scripts/           verify_keys.py · dev-env.sh · build-and-deploy.sh
pyproject.toml     deps + ruff/black/pytest config (Python >=3.12)
```
Integrations (OpenRouter / Apollo / Smartlead / Google / Stripe) arrive from Phase B.

## Local dev
Requires Python 3.12+ (Lambda runtime is `python3.12`). Uses the dev Aurora over the Data
API with your AWS creds — no local Postgres needed.
```bash
cd apps/api
uv venv --python 3.12 .venv && source .venv/bin/activate   # or: python3.12 -m venv
uv pip install -e ".[dev]"
source scripts/dev-env.sh                  # exports HOLDSLOT_DB_* from terraform output
uvicorn app.main:app --reload              # http://127.0.0.1:8000/health
pytest                                      # unit tests (add dev-env for acceptance)
ruff check . && black --check .             # lint + format
```

## Deploy
`AWS_PROFILE=holdslot ./scripts/build-and-deploy.sh` — builds the Linux x86_64 bundle,
publishes a Lambda version (SnapStart), shifts the `live` alias, smoke-tests `/health`.

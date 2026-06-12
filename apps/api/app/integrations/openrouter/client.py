"""OpenRouter adapter — the single seam every LLM feature calls through (B3).

Design invariants:
  * **Lazy / SnapStart-safe** — no network, no Secrets Manager, no RNG at import. The key +
    model config load on first use and are cached.
  * **Strict structured output** — sends `response_format: json_schema` (`strict:true`), the
    `models` fallback array (gemini-2.5-flash-lite → gpt-5-mini), and
    `provider.require_parameters:true` so only schema-honoring hosts serve the request.
  * **Observability built in** — every call persists an append-only `LlmCall` row (served
    model, tokens, cost, latency, status, retries, raw completion) in its OWN transaction, so
    telemetry is durable even when the caller's request later fails. The row id is returned so
    callers (B4) can link a `ResearchSpec` to the exact call that produced it.
  * **Bounded retry on parse failure** — a malformed-JSON completion is retried once; a second
    failure is recorded as `status=parse_error` (with the raw payload) and raised, never
    swallowed.

Uses stdlib `urllib` (no runtime HTTP dependency added) — same choice as `verify_keys.py`.
"""

from __future__ import annotations

import json
import logging
import os
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from functools import lru_cache

import boto3

log = logging.getLogger("holdslot.openrouter")

API_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_TIMEOUT = 25  # seconds; under the 30s Lambda timeout

# Locked model decision (2026-06-12). Used as the fallback when the secret omits them, so the
# adapter works even before the secret carries `default_model`/`models` (B0 secret write).
DEFAULT_MODEL = "google/gemini-2.5-flash-lite"
FALLBACK_MODELS = ["google/gemini-2.5-flash-lite", "openai/gpt-5-mini"]


class LlmError(RuntimeError):
    """An LLM call that could not return schema-valid JSON. Carries the telemetry row id."""

    def __init__(self, message: str, *, status: str, llm_call_id: str | None = None) -> None:
        super().__init__(message)
        self.status = status
        self.llm_call_id = llm_call_id


@dataclass
class OpenRouterConfig:
    api_key: str
    models: list[str]


@lru_cache(maxsize=1)
def _config() -> OpenRouterConfig:
    """Read `{prefix}/openrouter` once. Falls back to the locked model list if absent."""
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    sm = boto3.client("secretsmanager", region_name=region)
    raw = sm.get_secret_value(SecretId=f"{prefix}/openrouter")["SecretString"]
    sec = json.loads(raw)
    models = sec.get("models") or ([sec["default_model"]] if sec.get("default_model") else None)
    return OpenRouterConfig(api_key=sec["api_key"], models=models or list(FALLBACK_MODELS))


def reset_config() -> None:
    _config.cache_clear()


@dataclass
class CallOutcome:
    status: str  # ok | parse_error | timeout | error
    data: dict | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    cost_usd: float | None
    latency_ms: int | None
    retries: int
    raw: dict | None
    error_detail: str | None = None  # human-readable cause for non-ok outcomes


# Transport status codes worth one retry (transient upstream / rate limit).
_RETRYABLE_HTTP = {408, 409, 425, 429, 500, 502, 503, 504}


def _envelope_error_detail(err: object) -> str:
    if isinstance(err, dict):
        return str(err.get("message") or err)[:300]
    return str(err)[:300]


def _post(body: dict, *, timeout: int) -> dict:
    """POST to OpenRouter and return the parsed response envelope. Raises on transport error."""
    cfg = _config()
    req = urllib.request.Request(
        API_URL,
        data=json.dumps(body).encode(),
        headers={
            "Authorization": f"Bearer {cfg.api_key}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode())


def _build_body(messages: list[dict], schema: dict, models: list[str]) -> dict:
    return {
        "models": models,
        "provider": {"require_parameters": True},
        "response_format": {"type": "json_schema", "json_schema": schema},
        "messages": messages,
        "usage": {"include": True},
    }


def _execute(
    messages: list[dict],
    schema: dict,
    *,
    models: list[str] | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    max_retries: int = 1,
) -> CallOutcome:
    """Pure HTTP + parse + timing (no DB).

    Retries once on a transient transport failure (timeout / 5xx / 429) and once on a
    malformed-JSON completion. A 401/403 invalidates the cached key so a rotation is picked
    up on the next call without waiting for a cold start.
    """
    models = models or _config().models
    body = _build_body(messages, schema, models)
    started = time.monotonic()
    retries = 0

    def ms() -> int:
        return int((time.monotonic() - started) * 1000)

    for attempt in range(max_retries + 1):
        try:
            resp = _post(body, timeout=timeout)
        except urllib.error.HTTPError as e:
            snippet = ""
            try:
                snippet = e.read().decode("utf-8", "replace")[:300]
            except Exception:
                pass
            if e.code in (401, 403):
                # Stale/rotated key — drop the cache so the next call refetches.
                reset_config()
            if e.code in _RETRYABLE_HTTP and attempt < max_retries:
                retries += 1
                continue
            return CallOutcome(
                status="error",
                data=None,
                model=None,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=ms(),
                retries=retries,
                raw={"http_status": e.code, "body": snippet},
                error_detail=f"HTTP {e.code}: {snippet[:160]}",
            )
        except (TimeoutError, urllib.error.URLError) as e:
            is_timeout = isinstance(e, TimeoutError) or "timed out" in str(getattr(e, "reason", e))
            if attempt < max_retries:
                retries += 1
                continue
            return CallOutcome(
                status="timeout" if is_timeout else "error",
                data=None,
                model=None,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=ms(),
                retries=retries,
                raw=None,
                error_detail=("request timed out" if is_timeout else str(e)[:200]),
            )
        except Exception as e:
            return CallOutcome(
                status="error",
                data=None,
                model=None,
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=ms(),
                retries=retries,
                raw=None,
                error_detail=repr(e)[:200],
            )

        # OpenRouter can return HTTP 200 with an {"error": {...}} envelope (e.g. insufficient
        # credits, no schema-honoring provider). Surface it as a real error, not a parse_error.
        if resp.get("error") and not resp.get("choices"):
            return CallOutcome(
                status="error",
                data=None,
                model=resp.get("model"),
                input_tokens=None,
                output_tokens=None,
                cost_usd=None,
                latency_ms=ms(),
                retries=retries,
                raw=resp,
                error_detail=_envelope_error_detail(resp.get("error")),
            )

        usage = resp.get("usage") or {}
        content = (resp.get("choices") or [{}])[0].get("message", {}).get("content")
        try:
            parsed = json.loads(content) if content is not None else None
            if not isinstance(parsed, dict):
                raise ValueError("completion was not a JSON object")
        except (json.JSONDecodeError, ValueError, TypeError):
            if attempt < max_retries:
                retries += 1
                continue
            return CallOutcome(
                status="parse_error",
                data=None,
                model=resp.get("model"),
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
                cost_usd=usage.get("cost"),
                latency_ms=ms(),
                retries=retries,
                raw=resp,
                error_detail="completion was not schema-valid JSON",
            )

        return CallOutcome(
            status="ok",
            data=parsed,
            model=resp.get("model"),
            input_tokens=usage.get("prompt_tokens"),
            output_tokens=usage.get("completion_tokens"),
            cost_usd=usage.get("cost"),
            latency_ms=ms(),
            retries=retries,
            raw=resp,
        )

    # Unreachable, but keep the type checker happy.
    return CallOutcome(
        status="error",
        data=None,
        model=None,
        input_tokens=None,
        output_tokens=None,
        cost_usd=None,
        latency_ms=None,
        retries=retries,
        raw=None,
        error_detail="exhausted retries",
    )


def _persist(
    session_factory, tenant_id, purpose: str, prompt_version: str | None, outcome: CallOutcome
) -> str:
    """Write the LlmCall telemetry row in its own transaction; return its id as a string."""
    from app.core.db import ensure_awake
    from app.models import LlmCall

    db = session_factory()
    try:
        ensure_awake(db)  # this is a fresh session; make sure Aurora is up before writing
        row = LlmCall(
            tenant_id=tenant_id,
            purpose=purpose,
            prompt_version=prompt_version,
            status=outcome.status,
            model=outcome.model,
            input_tokens=outcome.input_tokens,
            output_tokens=outcome.output_tokens,
            cost_usd=outcome.cost_usd,
            latency_ms=outcome.latency_ms,
            retries=outcome.retries,
            raw=outcome.raw,
        )
        db.add(row)
        db.commit()
        return str(row.id)
    finally:
        db.close()


@dataclass
class StructuredResult:
    data: dict
    llm_call_id: str | None
    model: str | None


def structured_completion(
    *,
    tenant_id,
    purpose: str,
    messages: list[dict],
    schema: dict,
    prompt_version: str | None = None,
    timeout: int = DEFAULT_TIMEOUT,
    session_factory=None,
) -> StructuredResult:
    """Run one strict-`json_schema` completion, persist telemetry, return the parsed object.

    Telemetry is written for every outcome (ok / parse_error / timeout / error). On any
    non-ok status an `LlmError` is raised carrying the persisted `llm_call_id`. A telemetry
    *write* failure never destroys a successful completion — the result is still returned
    (with `llm_call_id=None`), since the LLM call was already made (and billed).
    """
    if session_factory is None:
        from app.core.db import get_session

        session_factory = get_session

    outcome = _execute(messages, schema, timeout=timeout)
    try:
        call_id: str | None = _persist(session_factory, tenant_id, purpose, prompt_version, outcome)
    except Exception:
        log.exception("llm_call telemetry write failed (purpose=%s)", purpose)
        call_id = None
    if outcome.status != "ok" or outcome.data is None:
        detail = f": {outcome.error_detail}" if outcome.error_detail else ""
        raise LlmError(
            f"OpenRouter call failed ({outcome.status}){detail}",
            status=outcome.status,
            llm_call_id=call_id,
        )
    return StructuredResult(data=outcome.data, llm_call_id=call_id, model=outcome.model)

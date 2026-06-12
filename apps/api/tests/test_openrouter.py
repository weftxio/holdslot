"""B3 tests — the OpenRouter adapter.

Unit tests (no network, no DB) cover the SnapStart import invariant and the parse/retry/
timeout paths by monkeypatching the HTTP layer. One gated integration test makes a real
completion and asserts the telemetry row lands.
"""

from __future__ import annotations

import os

import pytest

PROBE_SCHEMA = {
    "name": "Probe",
    "strict": True,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {"ok": {"type": "boolean"}},
        "required": ["ok"],
    },
}
MESSAGES = [{"role": "user", "content": 'Return {"ok": true}.'}]


def _fake_resp(content: str) -> dict:
    return {
        "model": "google/gemini-2.5-flash-lite",
        "choices": [{"message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }


def test_import_is_lazy_no_network_or_secret():
    """Importing the adapter must not load config (SnapStart invariant)."""
    import importlib

    mod = importlib.import_module("app.integrations.openrouter.client")
    mod.reset_config()
    # Config cache is empty until first use — proves no Secrets Manager call at import.
    assert mod._config.cache_info().currsize == 0


def test_execute_parses_valid_json(monkeypatch):
    from app.integrations.openrouter import client as c

    monkeypatch.setattr(c, "_post", lambda body, *, timeout: _fake_resp('{"ok": true}'))
    out = c._execute(MESSAGES, PROBE_SCHEMA, models=["m"])
    assert out.status == "ok"
    assert out.data == {"ok": True}
    assert out.input_tokens == 10 and out.output_tokens == 5
    assert out.cost_usd == 0.0001 and out.retries == 0


def test_execute_retries_once_then_parse_error(monkeypatch):
    from app.integrations.openrouter import client as c

    calls = {"n": 0}

    def bad(body, *, timeout):
        calls["n"] += 1
        return _fake_resp("this is not json")

    monkeypatch.setattr(c, "_post", bad)
    out = c._execute(MESSAGES, PROBE_SCHEMA, models=["m"])
    assert out.status == "parse_error"
    assert out.data is None
    assert calls["n"] == 2  # one retry
    assert out.retries == 1
    assert out.raw is not None  # raw payload kept for debugging


def test_execute_timeout(monkeypatch):
    from app.integrations.openrouter import client as c

    def boom(body, *, timeout):
        raise TimeoutError("timed out")

    monkeypatch.setattr(c, "_post", boom)
    out = c._execute(MESSAGES, PROBE_SCHEMA, models=["m"])
    assert out.status == "timeout"
    assert out.data is None and out.latency_ms is not None


# --- gated integration: real completion + telemetry row -----------------------

_DB = os.environ.get("HOLDSLOT_DB_CLUSTER_ARN")


@pytest.mark.skipif(not _DB, reason="integration — needs Aurora dev env + OpenRouter key")
def test_real_structured_completion_writes_telemetry():
    from sqlalchemy import select

    from app.core.db import get_session
    from app.integrations.openrouter.client import structured_completion
    from app.models import LlmCall, Tenant

    db = get_session()
    tenant_id = db.execute(select(Tenant.id).where(Tenant.slug == "holdslot")).scalar_one()

    res = structured_completion(
        tenant_id=tenant_id,
        purpose="b3_probe",
        messages=MESSAGES,
        schema=PROBE_SCHEMA,
        prompt_version="probe-v1",
    )
    assert isinstance(res.data, dict) and "ok" in res.data
    assert res.model  # served model recorded

    row = db.get(LlmCall, res.llm_call_id)
    assert row is not None
    assert row.status == "ok"
    assert row.input_tokens and row.input_tokens > 0
    assert row.cost_usd is not None and float(row.cost_usd) >= 0
    assert row.latency_ms and row.latency_ms > 0
    assert row.prompt_version == "probe-v1"
    # cleanup
    db.delete(row)
    db.commit()
    db.close()

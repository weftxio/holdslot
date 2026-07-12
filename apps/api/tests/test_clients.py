"""Client-router unit tests (non-Aurora). Pins the NF-4 llm-usage month-bucket SQL invariant."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.dialects import postgresql

from app.domains.clients.router import _llm_month_bucket
from app.models import LlmCall


def test_llm_month_bucket_uses_sql_literals_not_bound_params():
    """Regression (live-caught bug): the month bucket's format args must render as inline SQL
    literals, so the SELECT and GROUP BY copies of the expression are textually identical. A bound
    param makes them differ and Postgres rejects the query with 'created_at must appear in the GROUP
    BY clause'. Compiling the same expression in both positions must contain the literal text."""
    month = _llm_month_bucket()
    q = (
        select(month.label("month"), LlmCall.purpose)
        .group_by(month, LlmCall.purpose)
        .order_by(month.desc())
    )
    sql = str(q.compile(dialect=postgresql.dialect()))
    # The whole bucket renders with inline literals — no bind-param placeholder inside it.
    assert "to_char(date_trunc('month', timezone('UTC', llm_call.created_at)), 'YYYY-MM')" in sql
    # And it appears in the GROUP BY too (identical text → Postgres accepts the grouping).
    assert sql.count(
        "to_char(date_trunc('month', timezone('UTC', llm_call.created_at)), 'YYYY-MM')"
    ) >= 2

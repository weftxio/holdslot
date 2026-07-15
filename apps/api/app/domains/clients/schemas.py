from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator


class ClientOut(BaseModel):
    slug: str
    name: str
    role: str


class LlmUsageRow(BaseModel):
    """One month × purpose × model bucket of `llm_call` telemetry (NF-4 AI-COGS rollup)."""

    month: str  # YYYY-MM (UTC)
    purpose: str
    model: str | None = None
    calls: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0


class LlmUsageOut(BaseModel):
    rows: list[LlmUsageRow] = Field(default_factory=list)
    total_cost_usd: float = 0.0
    total_calls: int = 0


class UiPrefs(BaseModel):
    """The typed view of a user's console UI preferences (stored as an opaque JSONB bag; unknown
    keys are ignored on the way out). Extend with new toggles as the console grows."""

    sidebar_collapsed: bool = False


class UiPrefsIn(BaseModel):
    """Partial update for UI prefs — only the fields present are merged into the stored bag, so a
    caller can set one toggle without clobbering the others."""

    sidebar_collapsed: bool | None = None


class MeOut(BaseModel):
    id: str
    email: str
    full_name: str | None = None
    clients: list[ClientOut]
    ui_prefs: UiPrefs = UiPrefs()


class ClientCreateIn(BaseModel):
    name: str

    @field_validator("name")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("name is required")
        return v


def slugify(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return slug or "client"

"""Runtime configuration.

Secrets (JWT keys) are pulled from AWS Secrets Manager on first use and cached — never at
import, so a SnapStart snapshot never captures them and the first post-restore invocation
fetches fresh. `reset_settings()` clears the cache if a rotation needs to be picked up.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache

import boto3


@dataclass(frozen=True)
class Settings:
    env: str
    region: str
    secrets_prefix: str
    db_cluster_arn: str
    db_secret_arn: str
    db_name: str
    jwt_signing_key: str
    jwt_refresh_key: str
    access_ttl_seconds: int = 30 * 60  # 30 min
    refresh_ttl_seconds: int = 30 * 24 * 60 * 60  # 30 days
    reset_ttl_seconds: int = 60 * 60  # 1 hour
    email_sender: str = "no-reply@tryholdslot.com"
    web_base_url: str = "https://tryholdslot.com"  # base for links in emails (e.g. reset)


def _get_secret_json(name: str, region: str) -> dict:
    client = boto3.client("secretsmanager", region_name=region)
    raw = client.get_secret_value(SecretId=name)["SecretString"]
    return json.loads(raw)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    region = os.environ.get("AWS_REGION") or os.environ.get("AWS_DEFAULT_REGION") or "us-east-1"
    secrets_prefix = os.environ.get("HOLDSLOT_SECRETS_PREFIX", "holdslot/prod")
    app_secret = _get_secret_json(f"{secrets_prefix}/app", region)
    return Settings(
        env=os.environ.get("HOLDSLOT_ENV", "dev"),
        region=region,
        secrets_prefix=secrets_prefix,
        db_cluster_arn=os.environ["HOLDSLOT_DB_CLUSTER_ARN"],
        db_secret_arn=os.environ["HOLDSLOT_DB_SECRET_ARN"],
        db_name=os.environ.get("HOLDSLOT_DB_NAME", "holdslot"),
        jwt_signing_key=app_secret["jwt_signing_key"],
        jwt_refresh_key=app_secret["jwt_refresh_key"],
        web_base_url=os.environ.get("HOLDSLOT_WEB_BASE_URL", "https://tryholdslot.com").rstrip("/"),
    )


def reset_settings() -> None:
    get_settings.cache_clear()

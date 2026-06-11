"""Transactional email via SES (best-effort).

While the sending domain's DKIM isn't yet in DNS / SES is in sandbox, sends will fail —
that must not break the request flow (e.g. password reset). We log and swallow errors, and
in non-prod we log the body so flows are testable without a deliverable inbox.
"""

from __future__ import annotations

import logging

import boto3
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import get_settings

log = logging.getLogger("holdslot.email")


def send_email(to: str, subject: str, body_text: str) -> bool:
    s = get_settings()
    if s.env != "prod":
        log.info("EMAIL (%s) to=%s subject=%s\n%s", s.env, to, subject, body_text)
    try:
        client = boto3.client("sesv2", region_name=s.region)
        client.send_email(
            FromEmailAddress=s.email_sender,
            Destination={"ToAddresses": [to]},
            Content={
                "Simple": {
                    "Subject": {"Data": subject},
                    "Body": {"Text": {"Data": body_text}},
                }
            },
        )
        return True
    except (BotoCoreError, ClientError) as e:
        log.warning("SES send failed (non-fatal) to=%s: %s", to, e)
        return False

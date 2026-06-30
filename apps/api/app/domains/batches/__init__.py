"""Phase D (S3) — Sendout batch + client approval.

`router.py` is the console (JWT, owner) surface: create/list/detail/decide batches, edit the
sendout template, and send the tokenized approval email. The public token-only external surface
lives in `domains/approvals/`. Both share `service.py` — the template/render helpers, the masking
primitives, and the one decision-write path.
"""

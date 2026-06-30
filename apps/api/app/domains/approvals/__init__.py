"""Phase D — the public, token-only client approval surface (no auth).

The token IS the credential; there is no `require_membership` guard and no `{client}` path segment —
the `approval_link` resolves the batch → tenant. `GET /approve/{token}` returns the MASKED view
(the anti-data-theft allow-list serializer — D's security core); `POST /approve/{token}/decide`
writes the per-prospect decision through the shared `domains/batches/service.apply_decision`.
"""

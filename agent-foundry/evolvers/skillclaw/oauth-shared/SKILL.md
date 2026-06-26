# Shared skill — OAuth-integration test-plan construction (collective pool)

Offered to all four agents in the api-tester/verify-third-party-oauth-integration build.
Local filesystem, air-gapped. Adoption is the user's call (staged, never auto-adopted).

Distilled, framework-agnostic reinforcements for emitting a faithful 5-stage OAuth flow plan:

- Emit exactly eleven keys; copy the ten context fields (provider, the five endpoints,
  client_id, redirect_uri, scope, state_min_length) unchanged from the brief.
- "stages" is exactly five objects in stage order 1..5, each verbatim:
  redirect/GET/authorize_endpoint, code_receipt/GET/callback_endpoint,
  token_exchange/POST/token_endpoint, access_token_use/GET/userinfo_endpoint,
  token_refresh/POST/refresh_endpoint.
- Reproduce every assertion key exactly and in order; never rename (no "status200",
  no "has_clientId"), never drop, never add, never reorder.
- Output only the single JSON object. Never send a request, follow a redirect, or guess
  any code/token/state/status — a separate program drives the real flow and records it.

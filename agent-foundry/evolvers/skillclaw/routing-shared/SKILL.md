# Shared skill — API-gateway routing test-plan construction

Distilled from the four api-tester / test-api-gateway-routing agents' sessions and
offered back to all of them (local filesystem, air-gapped). Adoption is staged for
the user — never auto-applied.

## What good looks like
- Emit ONE JSON object per route with exactly seven keys: route, method, headers,
  body, expected_backend, other_backends, down_test.
- route = route_path; method, headers, expected_backend, down_test copied unchanged.
- body = the brief's JSON object copied verbatim, or null when the brief says none —
  never add, remove, reorder, or alter a field (the gateway-tampering defect the suite
  must catch is in the gateway, not your plan).
- headers copied verbatim, INCLUDING Authorization exactly as given.
- other_backends = all_services with the single expected_backend removed, in order,
  and nothing else. This is the "every other backend must receive zero requests" set.
- Never send a request, contact a host, or guess a routing result — the harness sends
  to the gateway, queries each backend's /__admin/requests journal, and records.

## Failure modes seen
- Listing all_services (including expected) or none in other_backends.
- Dropping or rewriting the Authorization header.
- Injecting/normalizing a body field (false-clearing the in-transit mutation check).
- Flipping or omitting down_test (the service-down route expects exactly 503).

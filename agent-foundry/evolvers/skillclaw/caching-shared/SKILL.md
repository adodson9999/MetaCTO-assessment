# Shared skill — caching-headers test-plan construction (api-tester)

Distilled, cross-agent guidance for building a faithful caching test plan. Local
filesystem pool (air-gapped). Offered to all four agents; adoption is staged, never auto.

- The cacheable GET, the PUT update, and the put/patch/delete mutations target the SINGLE
  record path `collection_path + "/" + target_id` (no query string, no trailing slash) —
  never the bare collection listing. Only the POST mutation targets `collection_path + "/add"`.
- The update request must change a field (a different `title`) so a correct API would
  change the resource's ETag.
- Emit exactly the six keys; never assert, fabricate, or pre-fill any Cache-Control value,
  ETag value, status code, or response body — the harness records the real headers.
- One parseable JSON object per endpoint, nothing else around it.

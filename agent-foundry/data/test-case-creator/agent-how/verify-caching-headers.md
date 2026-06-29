# api-tester-verify-caching-headers — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for caching headers testing. Assert the setup preconditions hold before probing.
  2. GET a cacheable resource. Assert Cache-Control/ETag are present per docs.
  3. Re-request with a validator. Assert a 304 when unchanged.
  4. GET a non-cacheable resource. Assert no-cache is signaled.
  5. Aggregate every scenario result and record the outcome. Assert the caching header compliance and correctness is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: caching header compliance and correctness meets the gold threshold. Fail: a caching header diverges from docs.

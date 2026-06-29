# api-tester-test-api-gateway-routing — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for gateway routing testing. Assert the setup preconditions hold before probing.
  2. Send a request matching a route. Assert it forwards to the documented target.
  3. Send a request with no matching route. Assert a 404 per docs.
  4. Inspect the forwarded path. Assert it matches the route table.
  5. Aggregate every scenario result and record the outcome. Assert the route forwarding accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: route forwarding accuracy meets the gold threshold. Fail: a request routes to the wrong target.

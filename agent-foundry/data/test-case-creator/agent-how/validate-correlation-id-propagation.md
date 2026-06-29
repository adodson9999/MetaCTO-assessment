# api-tester-validate-correlation-id-propagation — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for correlation-id propagation testing. Assert the setup preconditions hold before probing.
  2. Send a request with X-Correlation-ID. Assert the response echoes the same id.
  3. Send without the header. Assert a UUID-v4 id is generated.
  4. Inspect the logs. Assert the id appears in api and downstream logs.
  5. Aggregate every scenario result and record the outcome. Assert the propagation rate over all assertions is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: propagation rate over all assertions meets the gold threshold. Fail: the correlation id is not propagated.

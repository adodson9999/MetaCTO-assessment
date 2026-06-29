# api-tester-test-idempotency-of-endpoints — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for idempotency testing. Assert the setup preconditions hold before probing.
  2. Send the same PUT twice with a fixed key. Assert both responses are byte-identical.
  3. Send the same DELETE twice. Assert the second is a safe no-op.
  4. Replay a POST add with a fresh key. Assert a distinct resource is created.
  5. Aggregate every scenario result and record the outcome. Assert the idempotency compliance and correctness is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: idempotency compliance and correctness meets the gold threshold. Fail: a replayed PUT or DELETE diverges.

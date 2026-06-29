# api-tester-test-webhook-delivery — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for webhook delivery testing. Assert the setup preconditions hold before probing.
  2. Trigger an event that should fire a webhook. Assert a delivery attempt is recorded.
  3. Inspect the delivery payload. Assert it matches the documented schema.
  4. Force a failure. Assert a retry or dead-letter per docs.
  5. Aggregate every scenario result and record the outcome. Assert the webhook contract correctness and delivery rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: webhook contract correctness and delivery rate meets the gold threshold. Fail: a webhook is not delivered as documented.

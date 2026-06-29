# api-tester-test-event-driven-api-triggers — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for event-driven triggers testing. Assert the setup preconditions hold before probing.
  2. Emit a triggering event. Assert the documented action fires.
  3. Inspect processing. Assert the event is processed once.
  4. Force a failure. Assert a dead-letter or retry per docs.
  5. Aggregate every scenario result and record the outcome. Assert the event processing success rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: event processing success rate meets the gold threshold. Fail: an event is not processed as documented.

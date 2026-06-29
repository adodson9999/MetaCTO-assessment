# api-tester-test-long-polling-support — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for long polling testing. Assert the setup preconditions hold before probing.
  2. Open a long-poll request. Assert it holds open until an event or timeout.
  3. Trigger an event. Assert the held request returns it.
  4. Let it time out. Assert the documented timeout response.
  5. Aggregate every scenario result and record the outcome. Assert the long-poll response accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: long-poll response accuracy meets the gold threshold. Fail: long polling diverges from docs.

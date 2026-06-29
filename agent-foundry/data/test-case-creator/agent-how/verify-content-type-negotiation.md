# api-tester-verify-content-type-negotiation — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for content-type negotiation testing. Assert the setup preconditions hold before probing.
  2. Send Accept: application/json. Assert the response Content-Type is application/json.
  3. Send an unsupported Accept. Assert a 406 or documented default.
  4. POST with a wrong Content-Type. Assert a 4xx or documented handling.
  5. Aggregate every scenario result and record the outcome. Assert the content-type negotiation accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: content-type negotiation accuracy meets the gold threshold. Fail: negotiation diverges from the documented behavior.

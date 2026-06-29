# api-tester-validate-null-empty-fields — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for null and empty fields testing. Assert the setup preconditions hold before probing.
  2. Send a body with a null field. Assert the documented null handling holds.
  3. Send a body with an empty string field. Assert the documented empty handling holds.
  4. Omit an optional field. Assert the default is applied.
  5. Aggregate every scenario result and record the outcome. Assert the null/empty handling accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: null/empty handling accuracy meets the gold threshold. Fail: a null or empty field is mishandled.

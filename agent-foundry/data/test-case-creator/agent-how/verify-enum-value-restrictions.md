# api-tester-verify-enum-value-restrictions — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for enum restrictions testing. Assert the setup preconditions hold before probing.
  2. Send a valid enum value. Assert it is accepted.
  3. Send an out-of-set enum value. Assert a 4xx validation error.
  4. Send an empty enum value. Assert the documented handling.
  5. Aggregate every scenario result and record the outcome. Assert the enum validation rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: enum validation rate meets the gold threshold. Fail: an invalid enum value is accepted.

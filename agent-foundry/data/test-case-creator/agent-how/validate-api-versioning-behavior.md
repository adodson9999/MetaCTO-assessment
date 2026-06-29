# api-tester-validate-api-versioning-behavior — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for API versioning testing. Assert the setup preconditions hold before probing.
  2. Request the documented version. Assert it routes to that version.
  3. Request an unknown version. Assert a 4xx or documented default.
  4. Inspect the version header. Assert it matches the served version.
  5. Aggregate every scenario result and record the outcome. Assert the version routing accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: version routing accuracy meets the gold threshold. Fail: a version routes incorrectly.

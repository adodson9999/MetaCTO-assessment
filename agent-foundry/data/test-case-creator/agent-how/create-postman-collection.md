# api-tester-create-postman-collection — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for Postman collection testing. Assert the setup preconditions hold before probing.
  2. Build a request item per endpoint. Assert each item has method, url, and tests.
  3. Add the auth configuration. Assert protected requests carry auth.
  4. Validate the collection. Assert it is Newman-valid.
  5. Aggregate every scenario result and record the outcome. Assert the postman coverage rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: postman coverage rate meets the gold threshold. Fail: a collection item is missing or Newman-invalid.

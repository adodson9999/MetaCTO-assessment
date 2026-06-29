# api-tester-test-multipart-form-data-handling — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for multipart form data testing. Assert the setup preconditions hold before probing.
  2. POST a valid multipart form. Assert all parts are parsed.
  3. POST a malformed boundary. Assert a 4xx per docs.
  4. POST a field plus a file part. Assert both are handled.
  5. Aggregate every scenario result and record the outcome. Assert the multipart handling accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: multipart handling accuracy meets the gold threshold. Fail: a multipart request is mishandled.

# api-tester-validate-json-schema-responses — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for response JSON schema testing. Assert the setup preconditions hold before probing.
  2. GET a list endpoint. Assert every item validates against the documented schema.
  3. GET a single resource. Assert all required fields are present with correct types.
  4. Inspect a numeric field. Assert the field type matches the schema.
  5. Aggregate every scenario result and record the outcome. Assert the responses validated against schema is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: responses validated against schema meets the gold threshold. Fail: any response violates the documented schema.

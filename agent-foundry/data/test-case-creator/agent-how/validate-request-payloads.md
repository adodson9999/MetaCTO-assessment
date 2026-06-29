# api-tester-validate-request-payloads — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for request-body contract testing. Assert the setup preconditions hold before probing.
  2. Send the known-valid body to the create endpoint. Assert the response status is 2xx and the resource is created.
  3. Send a body missing a required field. Assert the response status is 4xx and the resource is not created.
  4. Send a body with a wrong-typed field. Assert the response status is 4xx with a validation error.
  5. Aggregate every scenario result and record the outcome. Assert the payload rejection rate over all labeled invalid bodies is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: payload rejection rate over all labeled invalid bodies meets the gold threshold. Fail: any invalid body is accepted with a 2xx.

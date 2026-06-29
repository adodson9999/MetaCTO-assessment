# api-tester-check-authorization-rules — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for authorization testing. Assert the setup preconditions hold before probing.
  2. Access an owner-only resource as the owner. Assert the response code is 200 with the resource.
  3. Access an owner-only resource as a different user. Assert the response code is 403 and no data is exposed.
  4. Access an admin route as a non-admin. Assert the response code is 403.
  5. Aggregate every scenario result and record the outcome. Assert the access-control accuracy over all role scenarios is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: access-control accuracy over all role scenarios meets the gold threshold. Fail: a denied role receives 2xx with data.

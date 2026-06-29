# api-tester-verify-crud-operation-integrity — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for CRUD integrity testing. Assert the setup preconditions hold before probing.
  2. Create a resource then read it. Assert the read returns the created fields.
  3. Update the resource. Assert the update is reflected on the next read.
  4. Delete the resource. Assert it is gone or marked deleted per docs.
  5. Aggregate every scenario result and record the outcome. Assert the CRUD integrity rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: CRUD integrity rate meets the gold threshold. Fail: a create/update/delete is not reflected.

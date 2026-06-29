# api-tester-test-bulk-operation-endpoints — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for bulk operations testing. Assert the setup preconditions hold before probing.
  2. Submit a valid bulk create. Assert all items are created.
  3. Submit a mixed valid/invalid batch. Assert valid items succeed and invalid are reported.
  4. Check the database delta. Assert it matches the valid item count.
  5. Aggregate every scenario result and record the outcome. Assert the bulk operation accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: bulk operation accuracy meets the gold threshold. Fail: a bulk batch is mishandled versus docs.

# api-tester-verify-audit-log-generation — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for audit logging testing. Assert the setup preconditions hold before probing.
  2. Perform an auditable action. Assert an audit entry is created.
  3. Inspect the entry. Assert it records actor, action, and timestamp.
  4. Perform a read-only action. Assert audit behavior matches docs.
  5. Aggregate every scenario result and record the outcome. Assert the audit log coverage and correctness is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: audit log coverage and correctness meets the gold threshold. Fail: an auditable action produces no correct entry.

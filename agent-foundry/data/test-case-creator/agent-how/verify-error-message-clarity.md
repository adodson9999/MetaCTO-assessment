# api-tester-verify-error-message-clarity — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for error message clarity testing. Assert the setup preconditions hold before probing.
  2. Trigger a validation error. Assert the error body names the offending field.
  3. Trigger a not-found error. Assert the error message is human-readable and specific.
  4. Trigger an auth error. Assert the message does not leak sensitive detail.
  5. Aggregate every scenario result and record the outcome. Assert the error-clarity pass rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: error-clarity pass rate meets the gold threshold. Fail: an error response is empty or leaks sensitive data.

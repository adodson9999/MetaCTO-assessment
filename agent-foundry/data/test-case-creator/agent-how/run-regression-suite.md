# api-tester-run-regression-suite — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for regression suite testing. Assert the setup preconditions hold before probing.
  2. Run the regression scenario set. Assert each scenario yields its expected result.
  3. Aggregate the results. Assert the pass/fail tally matches gold.
  4. Inspect a blocking failure. Assert it is flagged to block deployment.
  5. Aggregate every scenario result and record the outcome. Assert the regression report fidelity is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: regression report fidelity meets the gold threshold. Fail: a regression report field diverges from gold.

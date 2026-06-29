# api-tester-track-defect-density — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for defect density testing. Assert the setup preconditions hold before probing.
  2. Collect defects across modules. Assert each defect is attributed to a module.
  3. Compute density per module. Assert the ratio is defects over size.
  4. Rank modules. Assert the report ordering matches gold.
  5. Aggregate every scenario result and record the outcome. Assert the defect-density report accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: defect-density report accuracy meets the gold threshold. Fail: a density figure diverges from gold.

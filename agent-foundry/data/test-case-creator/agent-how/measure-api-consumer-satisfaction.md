# api-tester-measure-api-consumer-satisfaction — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for consumer satisfaction testing. Assert the setup preconditions hold before probing.
  2. Collect the satisfaction signals. Assert each signal is scored.
  3. Compute the NPS. Assert it equals promoters minus detractors.
  4. Produce the report. Assert the figures match gold.
  5. Aggregate every scenario result and record the outcome. Assert the NPS plan accuracy is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: NPS plan accuracy meets the gold threshold. Fail: the satisfaction report diverges from gold.

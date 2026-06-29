# api-tester-demo-metrics — node card

- **What:** Compute a satisfaction rate and publish a dashboard.
- **How:**
1. Read the seeded usage fixture.
2. Compute the response rate as responses ÷ recipients.
3. Publish the dashboard and emit results/metrics-dashboard.json.
- **Tools:** Python json.
- **Metric:** Response Validity = responses ÷ recipients. Pass: rate ≥ 30%. Fail: rate below 30% invalidates the report.

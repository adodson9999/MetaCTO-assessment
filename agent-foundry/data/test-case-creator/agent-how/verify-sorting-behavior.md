# api-tester-verify-sorting-behavior — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for sorting testing. Assert the setup preconditions hold before probing.
  2. Request ascending sort by a field. Assert the order is ascending.
  3. Request descending sort. Assert the order is descending.
  4. Request sort by an unknown field. Assert a 4xx or documented default.
  5. Aggregate every scenario result and record the outcome. Assert the sorting accuracy over all scenarios is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: sorting accuracy over all scenarios meets the gold threshold. Fail: a sort order is incorrect.

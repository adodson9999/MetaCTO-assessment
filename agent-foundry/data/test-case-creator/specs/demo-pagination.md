# api-tester-demo-pagination — node card

- **What:** Convert one collection's pagination contract into a read-only page plan.
- **How:**
1. Read the collection brief and parse it as JSON.
2. Send GET /products?limit=10&skip=0 and assert exactly 200 with ten items.
3. Write the page plan to results/pagination-plan.json.
4. Assert the third page skip equals twice the page size.
- **Tools:** Python json, urllib (read-only GET).
- **Metric:** Pagination Correctness Rate = correct pages / total pages. Pass: 100%. Fail: any page whose skip or limit is wrong.

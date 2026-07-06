# Test Cases — validate-search-and-filter-queries

Total: 7 | Pass: 7 | Fail: 0 | Blocked: 0

## TC-SEARCH-001
- **Title/Summary:** GET /products/search?q=phone returns matching products (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/search?q=phone.
  2. Assert status == 200.
  3. Assert products is array.
  4. Assert body has 'total'.
- **Test Data:** `{"scenario_id": "SEARCH-KEYWORD", "method": "GET", "path": "/products/search", "query": {"q": "phone"}, "body": null, "auth": null}`
- **Expected Result:** status == 200; products is array; body has 'total'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-002
- **Title/Summary:** GET /products/search?q=<nonsense> returns an empty product set (200, total 0)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/search?q=zzzqx-no-match.
  2. Assert status == 200.
  3. Assert products is array.
  4. Assert total == 0.
- **Test Data:** `{"scenario_id": "SEARCH-KEYWORD-EMPTY", "method": "GET", "path": "/products/search", "query": {"q": "zzzqx-no-match"}, "body": null, "auth": null}`
- **Expected Result:** status == 200; products is array; total == 0.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-003
- **Title/Summary:** GET /products/category/smartphones returns only that category (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/category/smartphones.
  2. Assert status == 200.
  3. Assert products is array.
  4. Assert every products[].category == 'smartphones'.
- **Test Data:** `{"scenario_id": "FILTER-CATEGORY", "method": "GET", "path": "/products/category/smartphones", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status == 200; products is array; every products[].category == 'smartphones'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-004
- **Title/Summary:** GET /products/categories returns the category list (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/categories.
  2. Assert status == 200.
  3. Assert $root is array.
- **Test Data:** `{"scenario_id": "FILTER-CATEGORY-LIST", "method": "GET", "path": "/products/categories", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status == 200; $root is array.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-005
- **Title/Summary:** GET /products?limit=5&skip=10 honours pagination (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products?limit=5&skip=10.
  2. Assert status == 200.
  3. Assert len(products) <= 5.
  4. Assert skip == 10.
  5. Assert limit == 5.
- **Test Data:** `{"scenario_id": "PAGE-LIMIT-SKIP", "method": "GET", "path": "/products", "query": {"limit": 5, "skip": 10}, "body": null, "auth": null}`
- **Expected Result:** status == 200; len(products) <= 5; skip == 10; limit == 5.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-006
- **Title/Summary:** GET /products?select=title,price returns only the selected fields (+id) (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products?limit=3&select=title%2Cprice.
  2. Assert status == 200.
  3. Assert every products[] keys ⊆ ['id', 'price', 'title'].
- **Test Data:** `{"scenario_id": "SELECT-FIELDS", "method": "GET", "path": "/products", "query": {"limit": 3, "select": "title,price"}, "body": null, "auth": null}`
- **Expected Result:** status == 200; every products[] keys ⊆ ['id', 'price', 'title'].
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-SEARCH-007
- **Title/Summary:** GET /products?sortBy=title&order=asc returns title-sorted products (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products?limit=10&sortBy=title&order=asc.
  2. Assert status == 200.
  3. Assert products sorted by title asc.
- **Test Data:** `{"scenario_id": "SORT-ASC", "method": "GET", "path": "/products", "query": {"limit": 10, "sortBy": "title", "order": "asc"}, "body": null, "auth": null}`
- **Expected Result:** status == 200; products sorted by title asc.
- **Actual Result:** HTTP 200.
- **Status:** Pass

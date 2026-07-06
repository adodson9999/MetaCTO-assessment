# Test Cases — verify-crud-operation-integrity

Total: 9 | Pass: 9 | Fail: 0 | Blocked: 0

## TC-CRUD-001
- **Title/Summary:** GET /products returns a paginated product list (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products?limit=5.
  2. Assert status == 200.
  3. Assert products is array.
  4. Assert body has 'total'.
  5. Assert len(products) <= 5.
- **Test Data:** `{"scenario_id": "CRUD-READ-LIST", "method": "GET", "path": "/products", "query": {"limit": 5}, "body": null, "auth": null}`
- **Expected Result:** status == 200; products is array; body has 'total'; len(products) <= 5.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-CRUD-002
- **Title/Summary:** GET /products/1 returns a single product with the expected shape (200)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/1.
  2. Assert status == 200.
  3. Assert id == 1.
  4. Assert body has 'title'.
  5. Assert body has 'price'.
- **Test Data:** `{"scenario_id": "CRUD-READ-ONE", "method": "GET", "path": "/products/1", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status == 200; id == 1; body has 'title'; body has 'price'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-CRUD-003
- **Title/Summary:** POST /products/add echoes the new product with an id (201, simulated)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add.
  2. Request body: {"title": "Forge Test Widget", "price": 42, "category": "groceries", "stock": 7}.
  3. Assert status in [200, 201].
  4. Assert title == 'Forge Test Widget'.
  5. Assert id is number.
- **Test Data:** `{"scenario_id": "CRUD-CREATE", "method": "POST", "path": "/products/add", "query": {}, "body": {"title": "Forge Test Widget", "price": 42, "category": "groceries", "stock": 7}, "auth": null, "note": "DummyJSON SIMULATES creation: it returns a success body + a fresh id but does NOT persist."}`
- **Expected Result:** status in [200, 201]; title == 'Forge Test Widget'; id is number.
- **Actual Result:** HTTP 201.
- **Status:** Pass

## TC-CRUD-004
- **Title/Summary:** GET the freshly-created product id returns 404 — documented non-persistence (not a bug)
- **Preconditions:** newProductId captured from CRUD-CREATE.
- **Test Steps:**
  1. Send GET /products/195.
  2. Assert status == 404.
  3. Assert message contains 'not found'.
- **Test Data:** `{"scenario_id": "CRUD-CREATE-NONPERSIST", "method": "GET", "path": "/products/{newProductId}", "query": {}, "body": null, "auth": null, "note": "Proves the simulated contract: the add succeeded but nothing was stored."}`
- **Expected Result:** status == 404; message contains 'not found'.
- **Actual Result:** HTTP 404. message='Product with id '195' not found'
- **Status:** Pass

## TC-CRUD-005
- **Title/Summary:** PUT /products/1 echoes the changed field (200, simulated)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send PUT /products/1.
  2. Request body: {"title": "Forge Updated Title"}.
  3. Assert status == 200.
  4. Assert id == 1.
  5. Assert title == 'Forge Updated Title'.
- **Test Data:** `{"scenario_id": "CRUD-UPDATE", "method": "PUT", "path": "/products/1", "query": {}, "body": {"title": "Forge Updated Title"}, "auth": null, "note": "Update is simulated: the changed field is echoed back, not persisted."}`
- **Expected Result:** status == 200; id == 1; title == 'Forge Updated Title'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-CRUD-006
- **Title/Summary:** DELETE /products/1 returns the product flagged isDeleted + deletedOn (200, simulated)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send DELETE /products/1.
  2. Assert status == 200.
  3. Assert isDeleted == True.
  4. Assert body has 'deletedOn'.
- **Test Data:** `{"scenario_id": "CRUD-DELETE", "method": "DELETE", "path": "/products/1", "query": {}, "body": null, "auth": null, "note": "Delete is simulated: it flags isDeleted/deletedOn but does not remove the record."}`
- **Expected Result:** status == 200; isDeleted == True; body has 'deletedOn'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-CRUD-007
- **Title/Summary:** GET /products/99999 returns 404 with a clear message
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /products/99999.
  2. Assert status == 404.
  3. Assert message contains 'not found'.
- **Test Data:** `{"scenario_id": "CRUD-READ-MISSING", "method": "GET", "path": "/products/99999", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status == 404; message contains 'not found'.
- **Actual Result:** HTTP 404. message='Product with id '99999' not found'
- **Status:** Pass

## TC-CRUD-008
- **Title/Summary:** PUT /products/99999 (nonexistent) returns 404
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send PUT /products/99999.
  2. Request body: {"title": "x"}.
  3. Assert status in [404, 400].
  4. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "CRUD-UPDATE-MISSING", "method": "PUT", "path": "/products/99999", "query": {}, "body": {"title": "x"}, "auth": null}`
- **Expected Result:** status in [404, 400]; body has 'message'.
- **Actual Result:** HTTP 404. message='Product with id '99999' not found'
- **Status:** Pass

## TC-CRUD-009
- **Title/Summary:** DELETE /products/99999 (nonexistent) returns 404
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send DELETE /products/99999.
  2. Assert status in [404, 400].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "CRUD-DELETE-MISSING", "method": "DELETE", "path": "/products/99999", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status in [404, 400]; body has 'message'.
- **Actual Result:** HTTP 404. message='Product with id '99999' not found'
- **Status:** Pass

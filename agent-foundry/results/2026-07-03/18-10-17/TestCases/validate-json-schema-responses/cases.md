# Test Cases — validate-json-schema-responses

Total: 22 | Pass: 0 | Fail: 0 | Blocked: 22

## TC-SCHEMA-001
- **Title/Summary:** Auth login: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-002
- **Title/Summary:** Products add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 201.
- **Status:** Blocked

## TC-SCHEMA-003
- **Title/Summary:** Products put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-004
- **Title/Summary:** Products patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-005
- **Title/Summary:** Posts add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /posts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 400.
- **Status:** Blocked

## TC-SCHEMA-006
- **Title/Summary:** Posts put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 400.
- **Status:** Blocked

## TC-SCHEMA-007
- **Title/Summary:** Posts patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-008
- **Title/Summary:** Todos add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /todos/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 400.
- **Status:** Blocked

## TC-SCHEMA-009
- **Title/Summary:** Todos put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-010
- **Title/Summary:** Todos patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-011
- **Title/Summary:** Users add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-012
- **Title/Summary:** Users put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-013
- **Title/Summary:** Users patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-014
- **Title/Summary:** Recipes add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 200.
- **Status:** Blocked

## TC-SCHEMA-015
- **Title/Summary:** Recipes put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-016
- **Title/Summary:** Recipes patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-017
- **Title/Summary:** Carts add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-018
- **Title/Summary:** Carts put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-019
- **Title/Summary:** Carts patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** Not captured.
- **Status:** Blocked

## TC-SCHEMA-020
- **Title/Summary:** Comments add: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /comments/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 400.
- **Status:** Blocked

## TC-SCHEMA-021
- **Title/Summary:** Comments put: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

## TC-SCHEMA-022
- **Title/Summary:** Comments patch: verify validate json schema responses returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned 404.
- **Status:** Blocked

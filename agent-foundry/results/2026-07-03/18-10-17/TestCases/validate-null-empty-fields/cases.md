# Test Cases — validate-null-empty-fields

Total: 136 | Pass: 33 | Fail: 103 | Blocked: 0

## TC-NULLF-001
- **Title/Summary:** Auth login: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-002
- **Title/Summary:** Products add: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-003
- **Title/Summary:** Products put: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-004
- **Title/Summary:** Products patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-005
- **Title/Summary:** Posts add: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /posts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-006
- **Title/Summary:** Posts put: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-007
- **Title/Summary:** Posts patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-008
- **Title/Summary:** Todos add: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /todos/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-009
- **Title/Summary:** Todos put: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-010
- **Title/Summary:** Todos patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-011
- **Title/Summary:** Firstname:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-012
- **Title/Summary:** Firstname:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-013
- **Title/Summary:** Firstname:empty string: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "empty-string"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-014
- **Title/Summary:** Firstname:whitespace only: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-015
- **Title/Summary:** Firstname:whitespace tab newline: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "whitespace-tab-newline"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-016
- **Title/Summary:** Firstname:whitespace unicode: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "whitespace-unicode"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-017
- **Title/Summary:** Firstname:zero length vs absent echo: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "required_state", "state": "zero-length-vs-absent-echo"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-018
- **Title/Summary:** Lastname:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-019
- **Title/Summary:** Lastname:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-020
- **Title/Summary:** Lastname:empty string: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "empty-string"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-021
- **Title/Summary:** Lastname:whitespace only: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-022
- **Title/Summary:** Lastname:whitespace tab newline: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "whitespace-tab-newline"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-023
- **Title/Summary:** Lastname:whitespace unicode: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "lastName", "category": "optional_state", "state": "whitespace-unicode"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-024
- **Title/Summary:** Age:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "age", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-025
- **Title/Summary:** Age:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "age", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-026
- **Title/Summary:** Age:integer zero: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "age", "category": "optional_state", "state": "integer-zero"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-027
- **Title/Summary:** Email:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-028
- **Title/Summary:** Email:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-029
- **Title/Summary:** Email:empty string: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "empty-string"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-030
- **Title/Summary:** Email:whitespace only: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-031
- **Title/Summary:** Email:whitespace tab newline: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "whitespace-tab-newline"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-032
- **Title/Summary:** Email:whitespace unicode: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "email", "category": "optional_state", "state": "whitespace-unicode"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-033
- **Title/Summary:** Users add: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "all_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-034
- **Title/Summary:** Firstname: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-NULLF-035
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-036
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-037
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-038
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-039
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-040
- **Title/Summary:** Firstname: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "firstName", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-NULLF-041
- **Title/Summary:** Users put: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-042
- **Title/Summary:** Users patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-043
- **Title/Summary:** Name:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-044
- **Title/Summary:** Name:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-045
- **Title/Summary:** Name:empty string: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "empty-string"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-046
- **Title/Summary:** Name:whitespace only: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-047
- **Title/Summary:** Name:whitespace tab newline: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "whitespace-tab-newline"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-048
- **Title/Summary:** Name:whitespace unicode: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "whitespace-unicode"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-049
- **Title/Summary:** Name:zero length vs absent echo: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "required_state", "state": "zero-length-vs-absent-echo"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-050
- **Title/Summary:** Ingredients:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-051
- **Title/Summary:** Ingredients:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-052
- **Title/Summary:** Ingredients:empty array: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "required_state", "state": "empty-array"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-053
- **Title/Summary:** Ingredients:empty array with null element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "required_state", "state": "empty-array-with-null-element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-054
- **Title/Summary:** Ingredients:null first array element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "required_state", "state": "null first array element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-055
- **Title/Summary:** Instructions:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "instructions", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-056
- **Title/Summary:** Instructions:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "instructions", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-057
- **Title/Summary:** Instructions:empty array: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "instructions", "category": "optional_state", "state": "empty-array"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-058
- **Title/Summary:** Instructions:empty array with null element: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "instructions", "category": "optional_state", "state": "empty-array-with-null-element"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-059
- **Title/Summary:** Instructions:null first array element: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "instructions", "category": "optional_state", "state": "null first array element"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-060
- **Title/Summary:** Preptimeminutes:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "prepTimeMinutes", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-061
- **Title/Summary:** Preptimeminutes:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "prepTimeMinutes", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-062
- **Title/Summary:** Preptimeminutes:integer zero: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "prepTimeMinutes", "category": "optional_state", "state": "integer-zero"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-063
- **Title/Summary:** Recipes add: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "all_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-064
- **Title/Summary:** Name: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-065
- **Title/Summary:** Ingredients: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "ingredients", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-066
- **Title/Summary:** Name+ingredients: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "combo_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-067
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-068
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-069
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-070
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-071
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-072
- **Title/Summary:** Name: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "name", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-NULLF-073
- **Title/Summary:** Recipes put: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-074
- **Title/Summary:** Recipes patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-075
- **Title/Summary:** Userid:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-076
- **Title/Summary:** Userid:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-077
- **Title/Summary:** Userid:empty string: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "empty-string"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-078
- **Title/Summary:** Userid:integer zero: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "integer-zero"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-079
- **Title/Summary:** Userid:boolean false: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "boolean-false"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-080
- **Title/Summary:** Userid:empty array: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "empty-array"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-081
- **Title/Summary:** Userid:empty object: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "empty-object"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-082
- **Title/Summary:** Userid:whitespace only: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 404.
- **Status:** Fail

## TC-NULLF-083
- **Title/Summary:** Userid:whitespace tab newline: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "whitespace-tab-newline"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 404.
- **Status:** Fail

## TC-NULLF-084
- **Title/Summary:** Userid:whitespace unicode: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "required_state", "state": "whitespace-unicode"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 404.
- **Status:** Fail

## TC-NULLF-085
- **Title/Summary:** Products:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-086
- **Title/Summary:** Products:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-087
- **Title/Summary:** Products:empty string: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-string"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-088
- **Title/Summary:** Products:integer zero: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "integer-zero"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-089
- **Title/Summary:** Products:boolean false: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "boolean-false"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-090
- **Title/Summary:** Products:empty array: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-array"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-091
- **Title/Summary:** Products:empty object: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-object"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-092
- **Title/Summary:** Products:whitespace only: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "whitespace-only"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-093
- **Title/Summary:** Products:empty array with null element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-array-with-null-element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 500.
- **Status:** Fail

## TC-NULLF-094
- **Title/Summary:** Products:null first array element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "null first array element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 500.
- **Status:** Fail

## TC-NULLF-095
- **Title/Summary:** Carts add: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "all_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-096
- **Title/Summary:** Userid: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-097
- **Title/Summary:** Products: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-098
- **Title/Summary:** Userid+products: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "combo_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-099
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-100
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-101
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-102
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-103
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-104
- **Title/Summary:** Userid: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "userId", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 400.
- **Status:** Fail

## TC-NULLF-105
- **Title/Summary:** Products:key absent: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "key-absent"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-106
- **Title/Summary:** Products:json null: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "json-null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-107
- **Title/Summary:** Products:empty array: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-array"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-108
- **Title/Summary:** Products:empty array with null element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "empty-array-with-null-element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 500.
- **Status:** Fail

## TC-NULLF-109
- **Title/Summary:** Products:null first array element: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "required_state", "state": "null first array element"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 500.
- **Status:** Fail

## TC-NULLF-110
- **Title/Summary:** Merge:key absent: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "merge", "category": "optional_state", "state": "key-absent"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-111
- **Title/Summary:** Merge:json null: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "merge", "category": "optional_state", "state": "json-null"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-112
- **Title/Summary:** Merge:boolean false: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "merge", "category": "optional_state", "state": "boolean-false"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-113
- **Title/Summary:** Merge:boolean true: verify validate null empty fields returns ?.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "merge", "category": "optional_state", "state": "boolean-true"}`
- **Expected Result:** The API returns ?.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-114
- **Title/Summary:** Carts put: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "all_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-115
- **Title/Summary:** Products: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "products", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-NULLF-116
- **Title/Summary:** Carts patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-117
- **Title/Summary:** Comments add: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /comments/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-118
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-119
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-120
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-121
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-122
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-123
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-124
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-125
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-126
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-127
- **Title/Summary:** ?:?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "required_state", "state": "?"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-128
- **Title/Summary:** Comments put: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "all_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-NULLF-129
- **Title/Summary:** ?: verify validate null empty fields returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "each_required_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-130
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-131
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-132
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-133
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-134
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-135
- **Title/Summary:** ?: verify validate null empty fields returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "?", "category": "string_null"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-NULLF-136
- **Title/Summary:** Comments patch: verify validate null empty fields returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

# Test Cases — validate-request-payloads

Total: 56 | Pass: 18 | Fail: 18 | Blocked: 20

## TC-REQPAY-001
- **Title/Summary:** Auth login: verify validate request payloads returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "valid"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 200.
- **Status:** Pass

## TC-REQPAY-002
- **Title/Summary:** Auth login: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "inv_all_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-003
- **Title/Summary:** Username:key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-004
- **Title/Summary:** Password:key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-005
- **Title/Summary:** Username,password:key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username,password", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-006
- **Title/Summary:** Username:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-007
- **Title/Summary:** Username:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-008
- **Title/Summary:** Username:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-009
- **Title/Summary:** Username:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-010
- **Title/Summary:** Password:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-011
- **Title/Summary:** Password:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-012
- **Title/Summary:** Password:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-013
- **Title/Summary:** Expiresinmins:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "expiresInMins", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-REQPAY-014
- **Title/Summary:** Expiresinmins:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "expiresInMins", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-REQPAY-015
- **Title/Summary:** Expiresinmins:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "expiresInMins", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-016
- **Title/Summary:** Expiresinmins:?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "expiresInMins", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-REQPAY-017
- **Title/Summary:** ?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "inv_extra_field"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-REQPAY-018
- **Title/Summary:** ?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "inv_extra_field"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 200.
- **Status:** Fail

## TC-REQPAY-019
- **Title/Summary:** Username: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_maxlength"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-020
- **Title/Summary:** Username: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "username", "category": "inv_maxlength"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-021
- **Title/Summary:** Password: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_maxlength"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-022
- **Title/Summary:** Password: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "password", "category": "inv_maxlength"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 400.
- **Status:** Pass

## TC-REQPAY-023
- **Title/Summary:** Products add: verify validate request payloads returns 2xx.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "valid"}`
- **Expected Result:** The API returns 2xx.
- **Actual Result:** The API returned 201.
- **Status:** Pass

## TC-REQPAY-024
- **Title/Summary:** Products add: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "inv_all_null"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-025
- **Title/Summary:** The required string field (title role):key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required string field (title role)", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-026
- **Title/Summary:** The required numeric field (price role):key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required numeric field (price role)", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-027
- **Title/Summary:** Both required fields (title and price roles):key absent: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "both required fields (title and price roles)", "category": "inv_missing_required"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-028
- **Title/Summary:** The required string field (title role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required string field (title role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-029
- **Title/Summary:** The required string field (title role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required string field (title role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-030
- **Title/Summary:** The required numeric field (price role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required numeric field (price role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-031
- **Title/Summary:** The required numeric field (price role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the required numeric field (price role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-032
- **Title/Summary:** The optional integer field (stock role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the optional integer field (stock role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-033
- **Title/Summary:** The optional integer field (stock role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the optional integer field (stock role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-034
- **Title/Summary:** The optional integer field (stock role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the optional integer field (stock role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-035
- **Title/Summary:** The optional string field (category role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the optional string field (category role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-036
- **Title/Summary:** The optional string field (description role):?: verify validate request payloads returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"field": "the optional string field (description role)", "category": "inv_wrong_type"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned 201.
- **Status:** Fail

## TC-REQPAY-037
- **Title/Summary:** Products put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-038
- **Title/Summary:** Products patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /products/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-039
- **Title/Summary:** Posts add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /posts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-040
- **Title/Summary:** Posts put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-041
- **Title/Summary:** Posts patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /posts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-042
- **Title/Summary:** Todos add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /todos/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-043
- **Title/Summary:** Todos put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-044
- **Title/Summary:** Todos patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /todos/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-045
- **Title/Summary:** Users add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-046
- **Title/Summary:** Users put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-047
- **Title/Summary:** Users patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /users/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-048
- **Title/Summary:** Recipes add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /recipes/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-049
- **Title/Summary:** Recipes put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-050
- **Title/Summary:** Recipes patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /recipes/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-051
- **Title/Summary:** Carts add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /carts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-052
- **Title/Summary:** Carts put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-053
- **Title/Summary:** Carts patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /carts/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-054
- **Title/Summary:** Comments add: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /comments/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-055
- **Title/Summary:** Comments put: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PUT /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

## TC-REQPAY-056
- **Title/Summary:** Comments patch: verify validate request payloads returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send PATCH /comments/{id} to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Blocked

# Test Cases — validate-query-parameter-handling

Total: 12 | Pass: 0 | Fail: 12 | Blocked: 0

## TC-QPARAM-001
- **Title/Summary:** Missing required q: verify validate query parameter handling returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-002
- **Title/Summary:** Wrongtype limit nonnumeric: verify validate query parameter handling returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-003
- **Title/Summary:** Wrongtype skip nonnumeric: verify validate query parameter handling returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-004
- **Title/Summary:** Wrongtype order badenum: verify validate query parameter handling returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-005
- **Title/Summary:** Valid limit: verify validate query parameter handling returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-006
- **Title/Summary:** Valid limit filter: verify validate query parameter handling returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-007
- **Title/Summary:** Valid select: verify validate query parameter handling returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-008
- **Title/Summary:** Valid select filter: verify validate query parameter handling returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-009
- **Title/Summary:** Valid order: verify validate query parameter handling returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-010
- **Title/Summary:** Valid order filter: verify validate query parameter handling returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-011
- **Title/Summary:** Valid q: verify validate query parameter handling returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-QPARAM-012
- **Title/Summary:** Undocumented ignored: verify validate query parameter handling returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

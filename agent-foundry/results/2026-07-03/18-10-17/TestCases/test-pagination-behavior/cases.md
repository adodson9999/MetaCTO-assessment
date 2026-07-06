# Test Cases — test-pagination-behavior

Total: 18 | Pass: 0 | Fail: 18 | Blocked: 0

## TC-PAGE-001
- **Title/Summary:** Page1: verify test pagination behavior returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-002
- **Title/Summary:** Page1: verify test pagination behavior returns 10.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 10.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-003
- **Title/Summary:** Page1 has next: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-004
- **Title/Summary:** Page2: verify test pagination behavior returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-005
- **Title/Summary:** Page2: verify test pagination behavior returns 10.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 10.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-006
- **Title/Summary:** Page2 no overlap: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-007
- **Title/Summary:** Page2 has next: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-008
- **Title/Summary:** Page3: verify test pagination behavior returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-009
- **Title/Summary:** Page3: verify test pagination behavior returns 5.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 5.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-010
- **Title/Summary:** Page3 no overlap: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-011
- **Title/Summary:** Page3 is last: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-012
- **Title/Summary:** Union unique: verify test pagination behavior returns 25.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 25.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-013
- **Title/Summary:** Union zero duplicates: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-014
- **Title/Summary:** Union equals window: verify test pagination behavior returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-015
- **Title/Summary:** Invalid page size negative: verify test pagination behavior returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-016
- **Title/Summary:** Invalid page size zero: verify test pagination behavior returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-017
- **Title/Summary:** Invalid page size nonnumeric: verify test pagination behavior returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-PAGE-018
- **Title/Summary:** Invalid cursor: verify test pagination behavior returns 400_or_422.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400_or_422.
- **Actual Result:** The API returned missing.
- **Status:** Fail

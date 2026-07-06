# Test Cases — test-multipart-form-data-handling

Total: 9 | Pass: 0 | Fail: 9 | Blocked: 0

## TC-MPART-001
- **Title/Summary:** Create: verify test multipart form data handling returns 201.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 201.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-002
- **Title/Summary:** Text field a exact: verify test multipart form data handling returns exact.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns exact.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-003
- **Title/Summary:** Text field b exact: verify test multipart form data handling returns exact.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns exact.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-004
- **Title/Summary:** Document url: verify test multipart form data handling returns present.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns present.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-005
- **Title/Summary:** File md5 roundtrip: verify test multipart form data handling returns match.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns match.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-006
- **Title/Summary:** Persisted readback: verify test multipart form data handling returns persisted.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns persisted.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-007
- **Title/Summary:** Oversized rejected: verify test multipart form data handling returns 413.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 413.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-008
- **Title/Summary:** Missing required field: verify test multipart form data handling returns 400.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 400.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-MPART-009
- **Title/Summary:** Wrong content type: verify test multipart form data handling returns 415.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 415.
- **Actual Result:** The API returned missing.
- **Status:** Fail

# Test Cases — test-file-upload-and-download

Total: 14 | Pass: 0 | Fail: 14 | Blocked: 0

## TC-FILE-001
- **Title/Summary:** Upload 1kb: verify test file upload and download returns 201.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 201.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-002
- **Title/Summary:** Upload 1kb url: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-003
- **Title/Summary:** Upload max: verify test file upload and download returns 201.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 201.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-004
- **Title/Summary:** Upload max url: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-005
- **Title/Summary:** Upload over: verify test file upload and download returns 413.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 413.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-006
- **Title/Summary:** Upload over url: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-007
- **Title/Summary:** Upload invalid: verify test file upload and download returns 415.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 415.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-008
- **Title/Summary:** Upload invalid url: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-009
- **Title/Summary:** Download 1kb: verify test file upload and download returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-010
- **Title/Summary:** Download 1kb content type jpeg: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-011
- **Title/Summary:** Download 1kb md5 match: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-012
- **Title/Summary:** Download max: verify test file upload and download returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-013
- **Title/Summary:** Download max content type jpeg: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-FILE-014
- **Title/Summary:** Download max md5 match: verify test file upload and download returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

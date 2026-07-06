# Test Cases — verify-content-type-negotiation

Total: 5 | Pass: 0 | Fail: 5 | Blocked: 0

## TC-CTYPE-001
- **Title/Summary:** Accept application json: verify verify content type negotiation returns match.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns match.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-CTYPE-002
- **Title/Summary:** Accept application xml: verify verify content type negotiation returns match.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns match.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-CTYPE-003
- **Title/Summary:** Accept text csv: verify verify content type negotiation returns match.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns match.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-CTYPE-004
- **Title/Summary:** Accept text html unsupported: verify verify content type negotiation returns 406.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 406.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-CTYPE-005
- **Title/Summary:** Accept wildcard: verify verify content type negotiation returns match.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /products to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns match.
- **Actual Result:** The API returned missing.
- **Status:** Fail

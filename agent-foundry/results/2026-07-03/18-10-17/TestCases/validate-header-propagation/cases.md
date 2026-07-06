# Test Cases — validate-header-propagation

Total: 13 | Pass: 0 | Fail: 13 | Blocked: 0

## TC-HDRPROP-001
- **Title/Summary:** Plan correlation id exact: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-002
- **Title/Summary:** Plan header name exact: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-003
- **Title/Summary:** Plan with header: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-004
- **Title/Summary:** Plan no header: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-005
- **Title/Summary:** Plan assertions complete: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-006
- **Title/Summary:** Resp header echo exact: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned absent.
- **Status:** Fail

## TC-HDRPROP-007
- **Title/Summary:** Api log: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned false.
- **Status:** Fail

## TC-HDRPROP-008
- **Title/Summary:** Api log unmodified: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned absent.
- **Status:** Fail

## TC-HDRPROP-009
- **Title/Summary:** Downstream services: verify validate header propagation returns >=2.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns >=2.
- **Actual Result:** The API returned 0.
- **Status:** Fail

## TC-HDRPROP-010
- **Title/Summary:** Downstream log: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned n/a.
- **Status:** Fail

## TC-HDRPROP-011
- **Title/Summary:** No header uuid generated: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned absent.
- **Status:** Fail

## TC-HDRPROP-012
- **Title/Summary:** No header uuid in api log: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned n/a.
- **Status:** Fail

## TC-HDRPROP-013
- **Title/Summary:** No header uuid in downstream: verify validate header propagation returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET products_add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned n/a.
- **Status:** Fail

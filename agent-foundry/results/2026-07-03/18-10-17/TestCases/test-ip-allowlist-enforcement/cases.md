# Test Cases — test-ip-allowlist-enforcement

Total: 5 | Pass: 0 | Fail: 5 | Blocked: 0

## TC-IPALLOW-001
- **Title/Summary:** Allowlisted baseline: verify test ip allowlist enforcement returns 200:data.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /restricted/orders to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200:data.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-IPALLOW-002
- **Title/Summary:** Nonallowlisted baseline: verify test ip allowlist enforcement returns 403:nodata.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /restricted/orders to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 403:nodata.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-IPALLOW-003
- **Title/Summary:** Xff spoof rejected: verify test ip allowlist enforcement returns 403:nodata.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /restricted/orders to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 403:nodata.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-IPALLOW-004
- **Title/Summary:** Allowlist add allows: verify test ip allowlist enforcement returns 200:data.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /restricted/orders to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200:data.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-IPALLOW-005
- **Title/Summary:** Allowlist remove blocks: verify test ip allowlist enforcement returns 403:nodata.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET /restricted/orders to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 403:nodata.
- **Actual Result:** The API returned missing.
- **Status:** Fail

# Test Cases — test-ssl-tls-enforcement

Total: 17 | Pass: 0 | Fail: 17 | Blocked: 0

## TC-TLS-001
- **Title/Summary:** Plain http refused or redirected: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-002
- **Title/Summary:** Plain http zero api data: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-003
- **Title/Summary:** Tls1 0 refused: verify test ssl tls enforcement returns refused.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns refused.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-004
- **Title/Summary:** Tls1 1 refused: verify test ssl tls enforcement returns refused.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns refused.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-005
- **Title/Summary:** Tls1 2 accepted: verify test ssl tls enforcement returns accepted.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns accepted.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-006
- **Title/Summary:** Tls1 3 accepted: verify test ssl tls enforcement returns accepted.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns accepted.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-007
- **Title/Summary:** Tls1 2 http 200: verify test ssl tls enforcement returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-008
- **Title/Summary:** Tls1 3 http 200: verify test ssl tls enforcement returns 200.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns 200.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-009
- **Title/Summary:** Cert not expired: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-010
- **Title/Summary:** Cert cn or san match: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-011
- **Title/Summary:** Cert chain of trust ok: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-012
- **Title/Summary:** Cert not self signed: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-013
- **Title/Summary:** No weak cipher rc4: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-014
- **Title/Summary:** No weak cipher des: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-015
- **Title/Summary:** No weak cipher 3des: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-016
- **Title/Summary:** No weak cipher export: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

## TC-TLS-017
- **Title/Summary:** No weak cipher null: verify test ssl tls enforcement returns true.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send GET  to https://localhost:9443.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"note": "no explicit inputs for this case"}`
- **Expected Result:** The API returns true.
- **Actual Result:** The API returned missing.
- **Status:** Fail

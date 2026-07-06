# Test Cases — verify-enum-value-restrictions

Total: 4 | Pass: 0 | Fail: 4 | Blocked: 0

## TC-ENUM-001
- **Title/Summary:** Products add: verify verify enum value restrictions returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /products/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-ENUM-002
- **Title/Summary:** Users add: verify verify enum value restrictions returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /users/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-ENUM-003
- **Title/Summary:** Todos add: verify verify enum value restrictions returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /todos/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

## TC-ENUM-004
- **Title/Summary:** Posts add: verify verify enum value restrictions returns the expected result.
- **Preconditions:** API target reachable and authenticated where required; no special prior state required.
- **Test Steps:**
  1. Send POST /posts/add to http://localhost:8899.
  2. Read the HTTP response status code and body.
  3. Compare the observed result to the expected result.
- **Test Data:** `{"category": "_none_"}`
- **Expected Result:** The response matches the documented contract for this case.
- **Actual Result:** The API returned none.
- **Status:** Fail

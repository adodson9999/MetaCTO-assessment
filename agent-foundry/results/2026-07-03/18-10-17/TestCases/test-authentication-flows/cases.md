# Test Cases — test-authentication-flows

Total: 11 | Pass: 10 | Fail: 1 | Blocked: 0

## TC-AUTH-001
- **Title/Summary:** Login with valid credentials returns 200 + accessToken + refreshToken
- **Preconditions:** Seed user emilys/emilyspass exists.
- **Test Steps:**
  1. Send POST /auth/login.
  2. Request body: {"username": "emilys", "password": "emilyspass"}.
  3. Assert status == 200.
  4. Assert body has 'accessToken'.
  5. Assert body has 'refreshToken'.
  6. Assert username == 'emilys'.
- **Test Data:** `{"scenario_id": "AUTH-LOGIN-VALID", "method": "POST", "path": "/auth/login", "query": {}, "body": {"username": "emilys", "password": "emilyspass"}, "auth": null, "note": "Tokens returned in body and as cookies."}`
- **Expected Result:** status == 200; body has 'accessToken'; body has 'refreshToken'; username == 'emilys'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-AUTH-002
- **Title/Summary:** Login with wrong password is rejected (400)
- **Preconditions:** Valid username, invalid password.
- **Test Steps:**
  1. Send POST /auth/login.
  2. Request body: {"username": "emilys", "password": "wrong-password"}.
  3. Assert status in [400, 401].
  4. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-LOGIN-WRONGPASS", "method": "POST", "path": "/auth/login", "query": {}, "body": {"username": "emilys", "password": "wrong-password"}, "auth": null}`
- **Expected Result:** status in [400, 401]; body has 'message'.
- **Actual Result:** HTTP 400. message='Invalid credentials'
- **Status:** Pass

## TC-AUTH-003
- **Title/Summary:** Login with unknown username is rejected (400)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login.
  2. Request body: {"username": "no-such-user-zzz", "password": "whatever"}.
  3. Assert status in [400, 401].
  4. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-LOGIN-UNKNOWN", "method": "POST", "path": "/auth/login", "query": {}, "body": {"username": "no-such-user-zzz", "password": "whatever"}, "auth": null}`
- **Expected Result:** status in [400, 401]; body has 'message'.
- **Actual Result:** HTTP 400. message='Invalid credentials'
- **Status:** Pass

## TC-AUTH-004
- **Title/Summary:** Login with missing credentials is rejected (400)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/login.
  2. Assert status in [400, 401].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-LOGIN-MISSING-FIELDS", "method": "POST", "path": "/auth/login", "query": {}, "body": {}, "auth": null, "note": "Ambiguity: docs don't specify the missing-field error \u2014 assert 4xx + message."}`
- **Expected Result:** status in [400, 401]; body has 'message'.
- **Actual Result:** HTTP 400. message='Username and password required'
- **Status:** Pass

## TC-AUTH-005
- **Title/Summary:** GET /auth/me with a valid Bearer token returns the current user (200)
- **Preconditions:** A valid accessToken captured from AUTH-LOGIN-VALID.
- **Test Steps:**
  1. Send GET /auth/me with a valid Bearer token.
  2. Assert status == 200.
  3. Assert username == 'emilys'.
  4. Assert body has 'email'.
- **Test Data:** `{"scenario_id": "AUTH-ME-VALID", "method": "GET", "path": "/auth/me", "query": {}, "body": null, "auth": "bearer"}`
- **Expected Result:** status == 200; username == 'emilys'; body has 'email'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-AUTH-006
- **Title/Summary:** GET /auth/me without a token is rejected (401/403)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /auth/me with no Authorization header.
  2. Assert status in [401, 403].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-ME-MISSING", "method": "GET", "path": "/auth/me", "query": {}, "body": null, "auth": null}`
- **Expected Result:** status in [401, 403]; body has 'message'.
- **Actual Result:** HTTP 401. message='Access Token is required'
- **Status:** Pass

## TC-AUTH-007
- **Title/Summary:** GET /auth/me with a malformed/invalid token is rejected (401/403)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /auth/me with a malformed Bearer token.
  2. Assert status in [401, 403].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-ME-MALFORMED", "method": "GET", "path": "/auth/me", "query": {}, "body": null, "auth": "bad"}`
- **Expected Result:** status in [401, 403]; body has 'message'.
- **Actual Result:** HTTP 500. message='invalid signature' FAILED: status in [401, 403].
- **Status:** Fail

## TC-AUTH-008
- **Title/Summary:** GET /auth/me with an expired token is rejected (401/403)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /auth/me with an expired Bearer token.
  2. Assert status in [401, 403].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-ME-EXPIRED", "method": "GET", "path": "/auth/me", "query": {}, "body": null, "auth": "expired", "note": "Token minted with a past exp via the shared auth_spec recipe."}`
- **Expected Result:** status in [401, 403]; body has 'message'.
- **Actual Result:** HTTP 401. message='Token Expired!'
- **Status:** Pass

## TC-AUTH-009
- **Title/Summary:** GET /auth/me after logout (revoked) — JWT is stateless, so behaviour is a coverage gap
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send GET /auth/me with a revoked (post-logout) token.
  2. Assert status in [200, 401, 403].
- **Test Data:** `{"scenario_id": "AUTH-ME-REVOKED", "method": "GET", "path": "/auth/me", "query": {}, "body": null, "auth": "revoked", "note": "Ambiguity: DummyJSON JWTs are stateless; logout may NOT invalidate an issued token. Recorded, not asserted strictly."}`
- **Expected Result:** status in [200, 401, 403].
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-AUTH-010
- **Title/Summary:** POST /auth/refresh with a valid refreshToken mints a new accessToken (200)
- **Preconditions:** A valid refreshToken captured from AUTH-LOGIN-VALID.
- **Test Steps:**
  1. Send POST /auth/refresh with the captured refreshToken.
  2. Request body: {"refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MSwidXNlcm5hbWUiOiJlbWlseXMiLCJlbWFpbCI6ImVtaWx5LmpvaG5zb25AeC5kdW1teWpzb24uY29tIiwiZmlyc3ROYW1lIjoiRW1pbHkiLCJsYXN0TmFtZSI6IkpvaG5zb24iLCJnZW5kZXIiOiJmZW1hbGUiLCJpbWFnZSI6Imh0dHBzOi8vZHVtbXlqc29uLmNvbS9pY29uL2VtaWx5cy8xMjgiLCJpYXQiOjE3ODMxODQ5MDMsImV4cCI6MTc4NTc3NjkwM30.Uw2v7NlJXf7SGeFwNjIEjJ3E2eN7Pb8hElIqnd3xqMA"}.
  3. Assert status == 200.
  4. Assert body has 'accessToken'.
  5. Assert body has 'refreshToken'.
- **Test Data:** `{"scenario_id": "AUTH-REFRESH-VALID", "method": "POST", "path": "/auth/refresh", "query": {}, "body": {"refreshToken": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6MSwidXNlcm5hbWUiOiJlbWlseXMiLCJlbWFpbCI6ImVtaWx5LmpvaG5zb25AeC5kdW1teWpzb24uY29tIiwiZmlyc3ROYW1lIjoiRW1pbHkiLCJsYXN0TmFtZSI6IkpvaG5zb24iLCJnZW5kZXIiOiJmZW1hbGUiLCJpbWFnZSI6Imh0dHBzOi8vZHVtbXlqc29uLmNvbS9pY29uL2VtaWx5cy8xMjgiLCJpYXQiOjE3ODMxODQ5MDMsImV4cCI6MTc4NTc3NjkwM30.Uw2v7NlJXf7SGeFwNjIEjJ3E2eN7Pb8hElIqnd3xqMA"}, "auth": "refresh"}`
- **Expected Result:** status == 200; body has 'accessToken'; body has 'refreshToken'.
- **Actual Result:** HTTP 200.
- **Status:** Pass

## TC-AUTH-011
- **Title/Summary:** POST /auth/refresh without a refreshToken is rejected (401/403)
- **Preconditions:** Target reachable; no special prior state required.
- **Test Steps:**
  1. Send POST /auth/refresh.
  2. Assert status in [400, 401, 403].
  3. Assert body has 'message'.
- **Test Data:** `{"scenario_id": "AUTH-REFRESH-MISSING", "method": "POST", "path": "/auth/refresh", "query": {}, "body": {}, "auth": null}`
- **Expected Result:** status in [400, 401, 403]; body has 'message'.
- **Actual Result:** HTTP 401. message='Refresh token required'
- **Status:** Pass

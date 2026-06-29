# Auth Reference

## POST /auth/login
Returns an accessToken and a refreshToken on valid credentials.
The accessToken expires after expiresInMins minutes (default 60).

## GET /auth/me
This endpoint requires a valid `Authorization: Bearer <accessToken>` header.
When the Authorization header is missing or the token is invalid, the API returns 401 Unauthorized.

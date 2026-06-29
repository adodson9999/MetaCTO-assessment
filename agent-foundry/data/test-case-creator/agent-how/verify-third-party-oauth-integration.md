# api-tester-verify-third-party-oauth-integration — How spec

- **How:**
  1. Authenticate against the target and prepare the endpoint set for third-party OAuth testing. Assert the setup preconditions hold before probing.
  2. Begin the OAuth authorization flow. Assert a redirect to the provider.
  3. Exchange a valid code. Assert tokens are issued.
  4. Exchange an invalid code. Assert the flow fails per docs.
  5. Aggregate every scenario result and record the outcome. Assert the OAuth flow completion rate is computed over all scenarios.
- **Tools:** http
- **Metric:** Pass: OAuth flow completion rate meets the gold threshold. Fail: the OAuth flow diverges from docs.

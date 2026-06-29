#!/usr/bin/env python3
# Used by: shared — generates test-case how-specs across agents.
"""Generate extractable `- **How:**` step specs + a 40-agent manifest for the
test-case-creator producer, so its registry covers ALL 40 api-tester agents instead
of only the 5 demo specs (closes guardrail G7 / the producer-scope gap).

Each spec is grounded in what that agent actually tests (SEED below) and is emitted in
the exact format the producer's extractor requires:
  - numbered steps `N. ...` (extract_how + the step regex),
  - at least one `Assert ...` clause per step (drives expected_outcome),
  - a `- **Metric:**` line with `Fail: ...` (drives fail_condition),
  - a `- **Tools:**` line terminating the How section.

Writes:  data/test-case-creator/agent-how/<agent>.md   (one per agent)
         data/test-case-creator/manifest.full.json     (40 enabled entries)
The demo manifest is left intact at manifest.json; point the producer at the full one
with FORGE_TESTCASE_MANIFEST or by swapping manifest.json.

Usage:  python gen_testcase_howspecs.py
"""
from __future__ import annotations

import json
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
OUT_DIR = WS / "data" / "test-case-creator" / "agent-how"

# agent -> (subject, [ (action, assertion) per probe step ], metric_phrase, fail_phrase)
SEED: dict[str, tuple] = {
    "validate-request-payloads": ("request-body contract", [
        ("Send the known-valid body to the create endpoint", "Assert the response status is 2xx and the resource is created"),
        ("Send a body missing a required field", "Assert the response status is 4xx and the resource is not created"),
        ("Send a body with a wrong-typed field", "Assert the response status is 4xx with a validation error")],
        "payload rejection rate over all labeled invalid bodies", "any invalid body is accepted with a 2xx"),
    "verify-response-status-codes": ("HTTP status codes", [
        ("Send a valid GET to an existing resource", "Assert the response code is exactly 200"),
        ("Request a non-existent resource id", "Assert the response code is exactly 404"),
        ("Send a malformed request", "Assert the response code is in the 4xx class")],
        "status-code accuracy over all scenarios", "any endpoint returns the wrong status class"),
    "test-authentication-flows": ("authentication", [
        ("POST valid credentials to the login endpoint", "Assert an accessToken and refreshToken are returned"),
        ("Call a protected endpoint without a token", "Assert the response code is exactly 401"),
        ("Call a protected endpoint with an invalid token", "Assert the response code is exactly 401")],
        "authentication pass rate with FAR and FRR", "a request that should be denied is accepted"),
    "check-authorization-rules": ("authorization", [
        ("Access an owner-only resource as the owner", "Assert the response code is 200 with the resource"),
        ("Access an owner-only resource as a different user", "Assert the response code is 403 and no data is exposed"),
        ("Access an admin route as a non-admin", "Assert the response code is 403")],
        "access-control accuracy over all role scenarios", "a denied role receives 2xx with data"),
    "validate-json-schema-responses": ("response JSON schema", [
        ("GET a list endpoint", "Assert every item validates against the documented schema"),
        ("GET a single resource", "Assert all required fields are present with correct types"),
        ("Inspect a numeric field", "Assert the field type matches the schema")],
        "responses validated against schema", "any response violates the documented schema"),
    "test-pagination-behavior": ("pagination", [
        ("GET the first page with a limit", "Assert the item count equals the limit and total is reported"),
        ("GET a subsequent page with skip", "Assert the returned window matches skip and limit"),
        ("Request limit 0", "Assert the documented limit-0 behavior holds")],
        "pagination correctness over all scenarios", "a page returns the wrong window or total"),
    "verify-error-message-clarity": ("error message clarity", [
        ("Trigger a validation error", "Assert the error body names the offending field"),
        ("Trigger a not-found error", "Assert the error message is human-readable and specific"),
        ("Trigger an auth error", "Assert the message does not leak sensitive detail")],
        "error-clarity pass rate", "an error response is empty or leaks sensitive data"),
    "test-rate-limit-enforcement": ("rate limiting", [
        ("Send requests up to the documented limit", "Assert all are accepted with 2xx"),
        ("Send one request past the limit", "Assert the response code is 429"),
        ("Wait the window then retry", "Assert the request succeeds again")],
        "rate-limit contract correctness", "the limiter does not return 429 past the limit"),
    "validate-query-parameter-handling": ("query parameters", [
        ("Send a valid filter query parameter", "Assert the result set honors the filter"),
        ("Send an unknown query parameter", "Assert it is ignored or rejected per docs"),
        ("Send an invalid parameter value", "Assert a 4xx or documented fallback")],
        "query-parameter accuracy over all scenarios", "a parameter is mishandled versus docs"),
    "test-idempotency-of-endpoints": ("idempotency", [
        ("Send the same PUT twice with a fixed key", "Assert both responses are byte-identical"),
        ("Send the same DELETE twice", "Assert the second is a safe no-op"),
        ("Replay a POST add with a fresh key", "Assert a distinct resource is created")],
        "idempotency compliance and correctness", "a replayed PUT or DELETE diverges"),
    "verify-content-type-negotiation": ("content-type negotiation", [
        ("Send Accept: application/json", "Assert the response Content-Type is application/json"),
        ("Send an unsupported Accept", "Assert a 406 or documented default"),
        ("POST with a wrong Content-Type", "Assert a 4xx or documented handling")],
        "content-type negotiation accuracy", "negotiation diverges from the documented behavior"),
    "validate-null-empty-fields": ("null and empty fields", [
        ("Send a body with a null field", "Assert the documented null handling holds"),
        ("Send a body with an empty string field", "Assert the documented empty handling holds"),
        ("Omit an optional field", "Assert the default is applied")],
        "null/empty handling accuracy", "a null or empty field is mishandled"),
    "test-timeout-handling": ("timeout handling", [
        ("Send a normal request", "Assert it completes within the timeout"),
        ("Send a slow/oversized request", "Assert a documented timeout response"),
        ("Inspect the timeout response", "Assert the status and message are documented")],
        "timeout enforcement rate", "a timeout is not enforced as documented"),
    "verify-crud-operation-integrity": ("CRUD integrity", [
        ("Create a resource then read it", "Assert the read returns the created fields"),
        ("Update the resource", "Assert the update is reflected on the next read"),
        ("Delete the resource", "Assert it is gone or marked deleted per docs")],
        "CRUD integrity rate", "a create/update/delete is not reflected"),
    "test-concurrent-request-handling": ("concurrency", [
        ("Fire N concurrent creates", "Assert each succeeds without corruption"),
        ("Fire concurrent updates to one resource", "Assert the final state is consistent"),
        ("Check the post-run count", "Assert the count delta matches the operations")],
        "concurrent request success rate", "concurrency corrupts state or counts"),
    "validate-header-propagation": ("header propagation", [
        ("Send a request with a tracing header", "Assert the response echoes the header"),
        ("Send without the header", "Assert the documented default behavior"),
        ("Inspect downstream propagation", "Assert the header reaches downstream per docs")],
        "header propagation rate", "a header is not propagated as documented"),
    "test-webhook-delivery": ("webhook delivery", [
        ("Trigger an event that should fire a webhook", "Assert a delivery attempt is recorded"),
        ("Inspect the delivery payload", "Assert it matches the documented schema"),
        ("Force a failure", "Assert a retry or dead-letter per docs")],
        "webhook contract correctness and delivery rate", "a webhook is not delivered as documented"),
    "run-regression-suite": ("regression suite", [
        ("Run the regression scenario set", "Assert each scenario yields its expected result"),
        ("Aggregate the results", "Assert the pass/fail tally matches gold"),
        ("Inspect a blocking failure", "Assert it is flagged to block deployment")],
        "regression report fidelity", "a regression report field diverges from gold"),
    "track-defect-density": ("defect density", [
        ("Collect defects across modules", "Assert each defect is attributed to a module"),
        ("Compute density per module", "Assert the ratio is defects over size"),
        ("Rank modules", "Assert the report ordering matches gold")],
        "defect-density report accuracy", "a density figure diverges from gold"),
    "validate-api-versioning-behavior": ("API versioning", [
        ("Request the documented version", "Assert it routes to that version"),
        ("Request an unknown version", "Assert a 4xx or documented default"),
        ("Inspect the version header", "Assert it matches the served version")],
        "version routing accuracy", "a version routes incorrectly"),
    "test-ssl-tls-enforcement": ("TLS enforcement", [
        ("Connect over the secure scheme", "Assert the connection is accepted"),
        ("Attempt an insecure connection", "Assert it is rejected or redirected per docs"),
        ("Inspect the security headers", "Assert documented headers are present")],
        "TLS enforcement rate", "an insecure connection is allowed against docs"),
    "verify-caching-headers": ("caching headers", [
        ("GET a cacheable resource", "Assert Cache-Control/ETag are present per docs"),
        ("Re-request with a validator", "Assert a 304 when unchanged"),
        ("GET a non-cacheable resource", "Assert no-cache is signaled")],
        "caching header compliance and correctness", "a caching header diverges from docs"),
    "validate-correlation-id-propagation": ("correlation-id propagation", [
        ("Send a request with X-Correlation-ID", "Assert the response echoes the same id"),
        ("Send without the header", "Assert a UUID-v4 id is generated"),
        ("Inspect the logs", "Assert the id appears in api and downstream logs")],
        "propagation rate over all assertions", "the correlation id is not propagated"),
    "test-bulk-operation-endpoints": ("bulk operations", [
        ("Submit a valid bulk create", "Assert all items are created"),
        ("Submit a mixed valid/invalid batch", "Assert valid items succeed and invalid are reported"),
        ("Check the database delta", "Assert it matches the valid item count")],
        "bulk operation accuracy", "a bulk batch is mishandled versus docs"),
    "verify-audit-log-generation": ("audit logging", [
        ("Perform an auditable action", "Assert an audit entry is created"),
        ("Inspect the entry", "Assert it records actor, action, and timestamp"),
        ("Perform a read-only action", "Assert audit behavior matches docs")],
        "audit log coverage and correctness", "an auditable action produces no correct entry"),
    "validate-search-and-filter-queries": ("search and filter", [
        ("Search a known term", "Assert matching results are returned"),
        ("Apply a filter key/value", "Assert only matching items remain"),
        ("Search a non-existent term", "Assert an empty result set")],
        "filter accuracy over all scenarios", "a search or filter returns wrong results"),
    "test-file-upload-and-download": ("file upload/download", [
        ("Upload a valid file", "Assert it is accepted and retrievable"),
        ("Upload an oversized file", "Assert it is rejected per docs"),
        ("Upload an invalid mime type", "Assert it is rejected")],
        "file integrity and rejection rates", "a file operation diverges from docs"),
    "verify-sorting-behavior": ("sorting", [
        ("Request ascending sort by a field", "Assert the order is ascending"),
        ("Request descending sort", "Assert the order is descending"),
        ("Request sort by an unknown field", "Assert a 4xx or documented default")],
        "sorting accuracy over all scenarios", "a sort order is incorrect"),
    "test-event-driven-api-triggers": ("event-driven triggers", [
        ("Emit a triggering event", "Assert the documented action fires"),
        ("Inspect processing", "Assert the event is processed once"),
        ("Force a failure", "Assert a dead-letter or retry per docs")],
        "event processing success rate", "an event is not processed as documented"),
    "test-ip-allowlist-enforcement": ("IP allowlist", [
        ("Request from an allowlisted address", "Assert it is accepted"),
        ("Request from a non-allowlisted address", "Assert it is rejected with 403"),
        ("Inspect the rejection", "Assert no data is exposed")],
        "IP allowlist enforcement rate", "a non-allowlisted address receives 2xx"),
    "test-api-gateway-routing": ("gateway routing", [
        ("Send a request matching a route", "Assert it forwards to the documented target"),
        ("Send a request with no matching route", "Assert a 404 per docs"),
        ("Inspect the forwarded path", "Assert it matches the route table")],
        "route forwarding accuracy", "a request routes to the wrong target"),
    "verify-third-party-oauth-integration": ("third-party OAuth", [
        ("Begin the OAuth authorization flow", "Assert a redirect to the provider"),
        ("Exchange a valid code", "Assert tokens are issued"),
        ("Exchange an invalid code", "Assert the flow fails per docs")],
        "OAuth flow completion rate", "the OAuth flow diverges from docs"),
    "test-multipart-form-data-handling": ("multipart form data", [
        ("POST a valid multipart form", "Assert all parts are parsed"),
        ("POST a malformed boundary", "Assert a 4xx per docs"),
        ("POST a field plus a file part", "Assert both are handled")],
        "multipart handling accuracy", "a multipart request is mishandled"),
    "validate-retry-after-header-compliance": ("Retry-After compliance", [
        ("Exceed the rate limit", "Assert a 429 with a positive Retry-After header"),
        ("Wait the advertised duration then retry", "Assert the request succeeds"),
        ("Inspect the header value", "Assert it equals the documented window")],
        "Retry-After accuracy", "Retry-After is absent or wrong after a 429"),
    "test-soft-delete-behavior": ("soft delete", [
        ("Delete a resource", "Assert it is marked isDeleted with a deletedOn timestamp"),
        ("Read the soft-deleted resource", "Assert the documented visibility holds"),
        ("List the collection", "Assert soft-deleted items follow the documented rule")],
        "soft delete correctness", "a delete does not follow the documented soft-delete rule"),
    "validate-graphql-depth-limits": ("GraphQL depth limits", [
        ("Send a query within the depth limit", "Assert it succeeds"),
        ("Send a query exceeding the depth limit", "Assert it is rejected"),
        ("Inspect the rejection", "Assert the documented depth error")],
        "depth enforcement rate", "an over-deep query is not rejected"),
    "test-long-polling-support": ("long polling", [
        ("Open a long-poll request", "Assert it holds open until an event or timeout"),
        ("Trigger an event", "Assert the held request returns it"),
        ("Let it time out", "Assert the documented timeout response")],
        "long-poll response accuracy", "long polling diverges from docs"),
    "verify-enum-value-restrictions": ("enum restrictions", [
        ("Send a valid enum value", "Assert it is accepted"),
        ("Send an out-of-set enum value", "Assert a 4xx validation error"),
        ("Send an empty enum value", "Assert the documented handling")],
        "enum validation rate", "an invalid enum value is accepted"),
    "measure-api-consumer-satisfaction": ("consumer satisfaction", [
        ("Collect the satisfaction signals", "Assert each signal is scored"),
        ("Compute the NPS", "Assert it equals promoters minus detractors"),
        ("Produce the report", "Assert the figures match gold")],
        "NPS plan accuracy", "the satisfaction report diverges from gold"),
    "create-postman-collection": ("Postman collection", [
        ("Build a request item per endpoint", "Assert each item has method, url, and tests"),
        ("Add the auth configuration", "Assert protected requests carry auth"),
        ("Validate the collection", "Assert it is Newman-valid")],
        "postman coverage rate", "a collection item is missing or Newman-invalid"),
}


def how_block(agent: str) -> str:
    subject, steps, metric, fail = SEED[agent]
    lines = [
        f"# api-tester-{agent} — How spec",
        "",
        f"- **How:**",
        f"  1. Authenticate against the target and prepare the endpoint set for {subject} testing. Assert the setup preconditions hold before probing.",
    ]
    for i, (action, assertion) in enumerate(steps, start=2):
        lines.append(f"  {i}. {action}. {assertion}.")
    n = len(steps) + 2
    lines.append(f"  {n}. Aggregate every scenario result and record the outcome. Assert the {metric} is computed over all scenarios.")
    lines.append(f"- **Tools:** http")
    lines.append(f"- **Metric:** Pass: {metric} meets the gold threshold. Fail: {fail}.")
    lines.append("")
    return "\n".join(lines)


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = []
    for agent in SEED:
        spec_path = OUT_DIR / f"{agent}.md"
        spec_path.write_text(how_block(agent))
        manifest.append({
            "name": f"api-tester-{agent}",
            "spec_path": f"data/test-case-creator/agent-how/{agent}.md",
            "enabled": True,
        })
    man_path = WS / "data" / "test-case-creator" / "manifest.full.json"
    man_path.write_text(json.dumps(manifest, indent=2))
    print(f"wrote {len(manifest)} How specs to {OUT_DIR.relative_to(WS)} and {man_path.name}")


if __name__ == "__main__":
    main()

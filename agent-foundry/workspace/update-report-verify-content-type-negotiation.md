# Update Report — verify-content-type-negotiation, 20260703T003112

## Change applied
Expand this agent's lane to the COMPLETE content-negotiation contract it solely owns per RFC 9110 §12 (proactive negotiation) — RESPONSE negotiation (Accept per media type, 406 unsupported, `*/*` and `type/*` wildcards, q-value preference ordering, Accept-Charset, Accept-Encoding gzip/br/identity, malformed Accept) and REQUEST negotiation (Content-Type accepted/415, missing Content-Type default, charset-in-Content-Type) — while keeping it a pure negotiation-probe bug-finder that emits ONE JSON object whose `cases` array holds negotiation probes only, feature-agnostic (refer to every input only by role: the endpoint under test, its `kind`, its ordered supported response media types, the unsupported-media-type probe, the supported request Content-Type, the unsupported request Content-Type; never assume, hardcode, name, or mention any URL/path/host/resource/feature), with `expected_class` taken ONLY from `references/contract-oracle.md` ("Headers" row — negotiation headers correct; "Validation" row — malformed request never 5xx), and preserving all existing invariants below.

Mirror this agent's own golden.json case schema EXACTLY for every new case: each case object has `role` (string), `channel` (exactly `response` or `request`), `recipe` (object `{ "kind": "<KIND from closed vocab>", "header": "...", "media_type": "...", "assert": "..." }` carrying only the header name and media-type/token echoed byte-for-byte from the brief; `assert` present only where an outcome property is checked), `expected_class` (string), and `also_accept` (array). Keep the top-level object shape identical: `agent`, `lane`, `cases`, `out_of_scope` (null when in-lane), `baseline` (`{ "metric": "content_negotiation_fidelity", "value": 1.0 }`).

KEEP the existing cases unchanged (accept_supported_format_N per supported media type, accept_unsupported/406, accept_wildcard/`*/*`, accept_charset, accept_q_value, accept_encoding, content_type_supported, content_type_unsupported/415, content_type_missing, content_type_charset; plus accept_language ONLY if localization is documented).

ADD the following NEW cases, grouped by class, each with ALL golden-schema fields spelled out:

Class subtype wildcard (RFC 9110 §12.5.1 — `type/*` matches any subtype of a type):
- role `accept_type_wildcard`, channel `response`, recipe `{ "kind": "accept_type_wildcard", "header": "Accept", "media_type": "application/*", "assert": "supported_subtype_chosen" }`, expected_class `2xx`, also_accept `[]` — `application/*` selects a supported `application/…` representation.

Class q=0 exclusion & unacceptable-all (RFC 9110 §12.5.1 — `q=0` means "not acceptable"; if nothing is acceptable, 406):
- role `accept_q_zero_excludes`, channel `response`, recipe `{ "kind": "accept_q_value", "header": "Accept", "media_type": "application/json;q=0, application/xml;q=0.9", "assert": "q_zero_format_not_chosen" }`, expected_class `2xx`, also_accept `[]` — a `q=0` media type is excluded from selection and the remaining highest-q supported format is returned.
- role `accept_all_unacceptable_406`, channel `response`, recipe `{ "kind": "accept_media_type", "header": "Accept", "media_type": "application/unsupported-a, application/unsupported-b" }`, expected_class `406`, also_accept `[]` — when every requested type is unsupported, 406 Not Acceptable.

Class explicit identity / no-compression (RFC 9110 §12.5.3 — Accept-Encoding: identity forces an unencoded body; `identity;q=0` or `*;q=0` with no acceptable coding → 406):
- role `accept_encoding_identity`, channel `response`, recipe `{ "kind": "accept_encoding", "header": "Accept-Encoding", "media_type": "identity", "assert": "no_content_encoding_applied" }`, expected_class `2xx`, also_accept `["200"]` — an identity request yields an unencoded body (no Content-Encoding, or `identity`).
- role `accept_encoding_unsupported_coding`, channel `response`, recipe `{ "kind": "accept_encoding", "header": "Accept-Encoding", "media_type": "application/unsupported-coding", "assert": "falls_back_to_identity_or_406" }`, expected_class `2xx`, also_accept `["406"]` — an unsupported coding falls back to identity (unencoded) or 406, never a 5xx.

Class malformed Accept robustness (RFC 9110 §12.5.1 — a syntactically broken Accept must not crash the server):
- role `accept_malformed_header`, channel `response`, recipe `{ "kind": "accept_malformed", "header": "Accept", "media_type": "application/json;;q=,, text/", "assert": "handled_without_5xx" }`, expected_class `2xx`, also_accept `["406","400"]` — a malformed Accept is handled by returning a default representation, 406, or 400 — never a 5xx.

Class charset unsupported (RFC 9110 §12.5.2 — an unsupported requested charset yields the default or 406, never a crash):
- role `accept_charset_unsupported`, channel `response`, recipe `{ "kind": "accept_charset", "header": "Accept-Charset", "media_type": "x-unsupported-charset", "assert": "default_charset_or_406" }`, expected_class `2xx`, also_accept `["406"]` — an unsupported Accept-Charset yields the server default charset or 406.

Class request Content-Type parameter tolerance (RFC 9110 §8.3 — the base media type governs acceptance; extra parameters must not spuriously 415):
- role `content_type_wrong_charset_415_or_ignored`, channel `request`, recipe `{ "kind": "request_content_type_charset", "header": "Content-Type", "media_type": "application/json; charset=x-unsupported" }`, expected_class `2xx`, also_accept `["415"]` — a supported base type with an unsupported charset parameter is accepted (charset ignored/defaulted) or 415, never a 5xx.

New recipe KINDs added to the CLOSED recipe vocabulary (in addition to the existing accept_media_type, accept_wildcard, accept_charset, accept_q_value, accept_encoding, accept_language, request_content_type, request_content_type_missing, request_content_type_charset): `accept_type_wildcard`, `accept_malformed`. New `assert` outcome tokens added to the closed assertion set: `supported_subtype_chosen`, `q_zero_format_not_chosen`, `no_content_encoding_applied`, `falls_back_to_identity_or_406`, `handled_without_5xx`, `default_charset_or_406`. No recipe kind, header, media type, or assert token outside these closed sets may ever be emitted; echo runtime-supplied media types, header names, and tokens byte-for-byte with no reorder/normalize/re-encode/translate.

REMOVE / never emit (route to sibling owner, cite it): VERSION negotiation — Accept version, vendor `application/vnd.*.vN+json` media-type versioning, path/query version selection, and Deprecation/Sunset/successor-Link signalling (owned by api-tester-validate-api-versioning-behavior — this agent negotiates generic FORMAT/charset/encoding, never a version); the bare 406/415 STATUS-CODE-value conformance divorced from a negotiation probe (this agent OWNS 406/415 as negotiation OUTCOMES per §Boundary map, but never emits generic status-code cases for other codes — those are verify-response-status-codes'); Vary as a caching-header presence assertion (owned by api-tester-verify-caching-headers — this agent drives negotiation, the caching agent asserts Vary is emitted); Accept-Language localization UNLESS documented (never assume localization exists). On out-of-lane input emit a single out-of-lane error sentinel naming the owning sibling in `out_of_scope` and nothing else.

PRESERVE all invariants: emit exactly ONE JSON object and nothing else (no prose, no code fence, no commentary, no extra/renamed keys); emit negotiation recipes only — never send an HTTP request, set/read a real header against a host, or state/guess a concrete numeric status, response Content-Type, echoed charset, or Content-Encoding (a separate deterministic harness sends each probe and records the real status and response headers); feature-agnostic role-only references with fail-closed out-of-scope when no negotiation surface is provided; `expected_by_contract`/`expected_class` sourced ONLY from contract-oracle.md; the accept_supported_format probe is emitted once PER supported response media type in documented order; never carry an `also_accept` that swallows a standard code the contract fixes (406/415 stay primary where the contract fixes them); confine all file access to FORGE_WORKSPACE; comply with Articles G1–G11; retain the self-awareness/code-review clause (all produced code is reviewed by every agent in agents/code-review/ and must score ≥85, looping until it does).

New total case count: base 11 (one accept_supported_format per supported media type, here 3 → 11 concrete) + 8 new = 19 concrete cases (scales with the count of supported response media types; the 8 additions are fixed).

## ADDENDUM (v2 — exhaustive test-case + reporting standard)
When running update-agent for this agent, pass the Change prompt above AND this ADDENDUM together as a single change prompt.

**No-verdict role.** This agent is now a pure, exhaustive test-case generator in its lane. It authors every case and fills the Expected Result (the definition of correct behavior, sourced from the contract oracle and the given spec). It does NOT execute, does NOT judge, and emits NO deviations, verdicts, or pass/fail. For every case it sets `actual_result` = "TO BE FILLED DURING EXECUTION" and `status` = `Not Executed`; a separate judge agent later executes the case, fills the actual result, and decides whether it is a bug. This section is governed by `00-AUTHORING-STANDARD-exhaustive-testcases.md`.

**Test Case ID prefix:** `TC-CONNEG-NNN` (zero-padded, sequential, stable across runs).

**Render every case in the human-readable schema.** In addition to the machine `cases` above, emit each test case with ALL of these human fields, in plain language, maximum detail: `test_case_id`, `title`, `description`, `category` (`happy`|`negative`|`boundary`|`edge`|`broad`), `feature_under_test`, `preconditions`, `test_data`, `test_steps`, `expected_result`, `actual_result` (="TO BE FILLED DURING EXECUTION"), `status` (=`Not Executed`), `postconditions`, `severity_hint`, `references`, `tags`. Keep this agent's existing machine fields (`role`, `channel`, `recipe`, `expected_class`, `also_accept`) under a `machine` key on each case. Emit ONE JSON object with a `test_cases[]` array carrying every case.

**Lane-specific exhaustive coverage checklist (ASPECT = 406/415 content negotiation — generic FORMAT/charset/encoding only; VERSION negotiation and Vary-as-caching are siblings').**
- Happy: Accept for each supported response media type returns that representation (one case per supported type in documented order); a supported request Content-Type is accepted; missing request Content-Type applies the documented default.
- Negative: an unsupported Accept media type returns 406; an unsupported request Content-Type returns 415; when every requested type is unsupported, 406 Not Acceptable.
- Boundary: q-value preference — the highest-q supported type wins; q=0 excludes a type and the remaining highest-q supported format is returned; the exact tie/ordering edge.
- Edge: `*/*` and `type/*` (e.g. application/*) subtype wildcards select a supported representation; Accept-Encoding identity yields an unencoded body; an unsupported coding falls back to identity or 406 (never 5xx); a malformed Accept is handled with a default representation, 406, or 400 (never 5xx).
- Broad: Accept-Charset supported and unsupported (default charset or 406); charset-in-Content-Type on the request — supported base type with an unsupported charset parameter is accepted (charset ignored/defaulted) or 415, never 5xx; each supported media type, charset, and encoding enumerated as its own probe.
- Sibling owners for adjacent concerns: VERSION negotiation — Accept version, vendor application/vnd.*.vN+json, path/query version selection, Deprecation/Sunset/successor-Link → validate-api-versioning-behavior; the bare non-406/415 STATUS-CODE-value conformance → verify-response-status-codes (this agent owns 406/415 as negotiation OUTCOMES); Vary as a caching-header presence assertion → verify-caching-headers; Accept-Language localization emitted ONLY if localization is documented.

Coverage exhaustive in-lane, MECE across agents — no duplicate cases.
(tradeoff: False)

## Score
FLOOR: 1.0  ·  after: 100.0  ·  verdict: improved

## Backup
/Users/alexdodson/Downloads/Jarvis/assessment/MetaCTO-Assessment/agent-foundry/archives/update-verify-content-type-negotiation-20260703T003112

# Expanded `update-agent` prompt — api-tester-test-authentication-flows

This is the full change prompt to feed the **update-agent** skill. It expands your
original prompt with the ten decisions you made. Paste everything under
"INVOCATION" as the `<prompt>` to the skill (or run the invocation line directly).

> Global directives that govern every instruction below (your words):
> 1. **Spell out every detail like a task for someone who needs every step** — zero
>    ambiguity, concrete JSON examples for every rule.
> 2. **This agent's job is testing + reporting, not fabricating test cases.** It only
>    *specifies* (in JSON) what to send, what to expect, what to log, and what to
>    report; the harness builds the real credentials and executes.
> 3. **Log every single step, no exceptions** — decomposed to the most atomic action
>    possible.

---

## INVOCATION

```
update-agent api-tester-test-authentication-flows <paste the CHANGE below>
```

## CHANGE

Re-specify `api-tester-test-authentication-flows` as a **full JWT token-lifecycle
tester** for ONE API's complete lifecycle across exactly three in-lane endpoints —
`POST /auth/login`, `GET /auth/me`, `POST /auth/refresh` — replacing today's
scheme-based plan (`protected_endpoint` / `schemes` / `not_applicable`). The agent
still emits **only a single JSON object** and performs **no HTTP, no login, no
network**, with all file access confined to `FORGE_WORKSPACE`. Leave the third-party
authorization-code flow to **api-tester-verify-third-party-oauth-integration** and
role-based access control to **api-tester-check-authorization-rules**.

This is an **authorized, explicit metric move** (not a silent regression): the emitted
contract changes shape, so update `judge/api-tester/test-authentication-flows/metric.json`
and `score.py` to score the new lifecycle/case contract, and re-derive the golden
baseline as the post-update best. Record the move in the diff report.

### 1. Division of labor — JSON-only, but the JSON specifies *everything*

The agent emits one JSON object that is a **complete plan + execution + logging +
report contract**. It never fabricates real tokens. The shared deterministic harness
reads this JSON, builds each credential, sends it to the real endpoint, records the
real responses, writes the per-step log, and computes the report — by following the
JSON exactly. ("Test-case creation" = building concrete tokens/requests = the
harness; the agent's job is to *specify testing and reporting* exhaustively.)

### 2. Top-level JSON shape — grouped by endpoint, self-describing cases

```json
{
  "meta": {
    "api": "<name from brief>",
    "lane": "auth-flows",
    "in_lane_endpoints": ["POST /auth/login", "GET /auth/me", "POST /auth/refresh"],
    "generated_by": "api-tester-test-authentication-flows"
  },
  "flows": [
    { "endpoint": "login",   "method": "POST", "path": "/auth/login",   "cases": [ ... ] },
    { "endpoint": "me",      "method": "GET",  "path": "/auth/me",      "cases": [ ... ] },
    { "endpoint": "refresh", "method": "POST", "path": "/auth/refresh", "cases": [ ... ] }
  ],
  "out_of_scope": {
    "oauth_authorization_code_flow": "api-tester-verify-third-party-oauth-integration",
    "rbac_on_protected_resources":   "api-tester-check-authorization-rules"
  },
  "report_spec": {
    "metrics": ["auth_flow_pass_rate", "false_acceptance_rate", "false_rejection_rate"],
    "per_case": ["verdict"],
    "per_endpoint_rollup": true,
    "output": "results/runs/<run-id>/api-tester-test-authentication-flows.json",
    "log_output": "results/runs/<run-id>/steps.jsonl"
  }
}
```

Each case must be readable end-to-end in one place.

### 3. Case object schema (every key required)

```json
{
  "label": "login_valid",
  "method": "POST",
  "path": "/auth/login",
  "recipe": { "kind": "valid_credentials", "params": { "from": "brief.valid_credentials" } },
  "expected_class": "2xx",
  "also_accept": [],
  "expected_body": { "require_present": ["token"], "non_empty": ["token"] },
  "steps": [ ... see §4 ... ]
}
```

- **`expected_class`** is a single primary status-class string; **`also_accept`** is an
  array (possibly empty) of other acceptable classes. The harness's verdict passes
  **iff** `observed_class == expected_class` OR `observed_class ∈ also_accept`.
- **`expected_body`** rules (full assertions, including rotation + negatives):
  - valid login → `{"require_present":["token"],"non_empty":["token"]}`
  - valid refresh → `{"require_present":["access_token"],"non_empty":["access_token"],"require_rotated":{"field":"access_token","differs_from":"previous_access_token"}}` (proves the new access token ≠ the previous one)
  - every **failure** case → `{"require_absent":["token","access_token","refresh_token"]}` (no token may be returned — fail-closed security check)
  - field names are configurable with defaults (`token`, `access_token`, `refresh_token`); the harness uses the brief's documented names when present.

### 4. `steps` — maximally granular, every step logged (NO fixed count)

`steps` is a **variable-length** array decomposed to the **most atomic action
possible**. Every action, no matter how trivial, is its own step and carries
`"log": true` — there must be **no room for misinterpretation or ambiguity, every
single thing tracked**. The agent emits each planned step and its logging
requirement; the harness fills `observed`, `verdict`, and `ts` as it executes.

Fully worked example for `login_valid` (illustrative granularity — expand similarly
for every case):

```json
"steps": [
  {"n":1,  "action":"read_recipe",            "detail":"resolve kind=valid_credentials", "log":true},
  {"n":2,  "action":"resolve_param",          "detail":"load brief.valid_credentials.username", "log":true},
  {"n":3,  "action":"resolve_param",          "detail":"load brief.valid_credentials.password", "log":true},
  {"n":4,  "action":"build_request_body",     "detail":"{username, password}", "log":true},
  {"n":5,  "action":"set_method",             "detail":"POST", "log":true},
  {"n":6,  "action":"set_path",               "detail":"/auth/login", "log":true},
  {"n":7,  "action":"set_header",             "detail":"Content-Type: application/json", "log":true},
  {"n":8,  "action":"send_request",           "detail":"POST /auth/login", "log":true},
  {"n":9,  "action":"capture_status",         "detail":"observed status line", "log":true},
  {"n":10, "action":"parse_body",             "detail":"parse JSON response", "log":true},
  {"n":11, "action":"extract_field",          "detail":"read body.token", "log":true},
  {"n":12, "action":"assert_status_class",    "detail":"observed ∈ {2xx}", "log":true},
  {"n":13, "action":"assert_body_present",    "detail":"token present & non-empty", "log":true},
  {"n":14, "action":"decide_verdict",         "detail":"pass iff status+body both hold", "log":true},
  {"n":15, "action":"record_result",          "detail":"write case verdict", "log":true},
  {"n":16, "action":"write_log_entry",        "detail":"append step log line", "log":true}
]
```

Each emitted log line (written by the harness, one per step) carries:
`{run_id, case, step_n, action, detail, recipe_kind, recipe_params (redacted — never a
real token), method, path, expected_class, also_accept, expected_body, observed_status,
observed_body_keys, verdict, ts}`. **Every step is logged, no exceptions.**

### 5. Credential-recipe vocabulary (closed set — the agent may use only these)

| kind | params | used by |
|---|---|---|
| `valid_credentials` | `{from:"brief.valid_credentials"}` | login_valid |
| `wrong_password` | `{username:"brief.valid_credentials.username", password:"<deliberately-wrong>"}` | login_wrong_password |
| `unknown_user` | `{username:"<nonexistent>", password:"<any>"}` | login_unknown_user |
| `missing_fields` | `{omit:["password"]}` / `{omit:["username"]}` / `{omit:"all"}` (empty body) | login missing-field variants |
| `valid_token` | `{}` (harness obtains via a prior real login) | me_valid |
| `no_auth` | `{}` | me_missing |
| `truncate_token` | `{drop_chars:8, applies_to:"access_token"|"refresh_token"}` | malformed |
| `expired_token` | `{exp_delta_sec:-3600, applies_to:"access_token"|"refresh_token"}` | expired |
| `revoked_token` | `{revoke_via:"POST /auth/logout", applies_to:"access_token"|"refresh_token"}` | revoked |
| `valid_refresh_token` | `{obtain_via:"POST /auth/login -> read refresh_token"}` | refresh_valid |
| `no_refresh_token` | `{}` | refresh_missing |

`applies_to` defaults to `access_token`; the refresh token-tamper cases set
`applies_to:"refresh_token"`. The agent never invents a kind outside this table.

### 6. Coverage rule — the deterministic case generator (replaces "exactly 11")

Compute the case set **deterministically from the API brief**. For **each** in-lane
endpoint:

1. **Positive** valid case (2xx + body assertion).
2. **Missing-field matrix:** one `missing_fields` case omitting **each** required
   input field individually, **plus** one empty-body case (`omit:"all"`).
3. **Semantic negatives** where applicable: login also gets `wrong_password` and
   `unknown_user`.
4. **Token-tamper on every token-bearing call:** `malformed` / `expired` / `revoked`
   for **both** `/auth/me` (access token) **and** `/auth/refresh` (refresh token),
   plus the missing-token / missing-refresh case.

For the canonical brief (`login{username,password}`, `me{access token}`,
`refresh{refresh_token}`) this yields **exactly 16 cases**, none omitted, no extras:

```
login   : valid, wrong_password, unknown_user, missing_password, missing_username, missing_all   (6)
me      : valid, missing, malformed, expired, revoked                                              (5)
refresh : valid, missing(empty), malformed, expired, revoked                                       (5)
```

Per-case expected status (`expected_class` + `also_accept`):

```
login_valid            2xx  []            me_valid       2xx  []        refresh_valid     2xx  []
login_wrong_password   401  [400]         me_missing     401  [403]     refresh_missing   401  [400]
login_unknown_user     401  [400]         me_malformed   401  [403]     refresh_malformed 401  [403]
login_missing_password 400  []            me_expired     401  [403]     refresh_expired   401  [403]
login_missing_username 400  []            me_revoked     401  [403]     refresh_revoked   401  [403]
login_missing_all      400  []
```

This **supersedes the original "exactly eleven" line**: the set is now the
deterministic function of the brief's required fields (16 for the canonical case).

### 7. Guardrail — stay in lane, fail closed (three layers)

- **Layer 1 — system prompt.** The agent emits ONLY the in-lane contract (flows for
  `/auth/login`, `/auth/me`, `/auth/refresh`). It **never** emits an RBAC/authorization
  case or any third-party-OAuth stage. If the input asks for RBAC or OAuth, it emits
  **exactly one** error sentinel and nothing else:
  `{"error":"out_of_lane","reason":"<rbac|oauth>","handoff":{...}}`.
- **Layer 2 — `run.py` validator (all four frameworks).** Before the harness uses the
  plan, validate: only in-lane endpoints/labels present; no out-of-lane (RBAC/OAuth)
  case; the case set **equals** the coverage-rule set (no missing, no extra); schema
  valid. On **any** violation, **fail closed**: discard the output, write **no**
  results, exit **non-zero**, log the reason. Never accept a partial or strayed plan.
- **Layer 3 — `out_of_scope` handoff section** (kept in every plan) naming the two
  sibling agents, exactly as in §2.

### 8. Report + log spec

- **Metrics:** Auth Flow Pass Rate, False Acceptance Rate (FAR), False Rejection Rate
  (FRR), per-case verdict, per-endpoint rollup.
- **Outputs:** report → `results/runs/<run-id>/api-tester-test-authentication-flows.json`;
  step log → `results/runs/<run-id>/steps.jsonl` (one line per atomic step, §4).

### 9. Regression safety net (golden + pytest unit tests) — all four enforced

- **GOLDEN (byte-stable).** `tests/golden/api-tester/test-authentication-flows/golden.json`
  pins the **entire** expected plan for a **fixed canonical brief** (define it inline:
  `login{username,password}` with fixed valid credentials, `me` protected by access
  token, `refresh{refresh_token}`). **Deterministic key + case ordering** (the §6
  order). The post-update best plan for this brief becomes the new baseline
  (`golden_run.py --derive`).
- **UNIT TESTS (pytest):**
  1. **Exact golden match** — regenerate the plan for the canonical brief and assert
     it equals `golden.json` exactly (ordering fixed); any drift fails.
  2. **Schema + shape** — JSON Schema validates every case: required keys, types,
     `recipe.kind` ∈ vocabulary (§5), `expected_class` + `also_accept` array, a
     **non-empty** granular `steps[]` with `log:true` on **every** step, and the
     `expected_body` rules.
  3. **Full deterministic coverage** — every required case per endpoint present;
     `count == expected_count(brief)` (16 canonical); **fail if even one is missing**;
     reject any extra/unknown case.
  4. **Lane + security** — no RBAC/OAuth case anywhere; `out_of_scope` names exactly
     the two siblings; out-of-lane input → error sentinel + non-zero exit (fail
     closed); every failure case asserts **no token returned**; `*_valid` refresh
     asserts **rotation** (new ≠ previous); **every `step.log == true`**.

### 10. Apply through the full update-agent flow (do not skip any gate)

Apply the change across **all four frameworks** (LangGraph, CrewAI, Claude Code
subagent, Claude Agent SDK) `run.py` dispatchers **and** the judge `score.py` +
`metric.json`. Re-author every changed instruction line through the **four-member
debate gate one line at a time**; run the **determinism review** on the prompt; hold
the **95 code-quality floor** on every regenerated `run.py`/`score.py`; run the
**dynamic code-review gate** — every agent in `agents/code-review/` must score **≥ 85,
no exception, looping until it does** — over all four `run.py`, the judge `score.py`,
and any produced code; run **`/analyze`** for cross-artifact consistency; **re-judge**
and run the **10-round keep-if-improved tournament**; then **`verify_build` +
`verify_files`**, write the **EverOS memory** record and the **diff report**, and
satisfy the **no-bypass code-review completion contract** (receipt reviewer set ==
`agents/code-review/`). Add the **self-awareness clause** to the system prompt across
all four frameworks and the judge: all code the agent creates is reviewed by every
agent in `agents/code-review/` at ≥85, looping until it does, pointing to
`agents/code-review/` and `references/memory-everos.md`. The metric move is explicit
and authorized; the update must still hold-or-improve against the (re-derived)
baseline and pass the code-review gate.
```

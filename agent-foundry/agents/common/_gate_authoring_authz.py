"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved instruction line of the authorization-rules task, and emits, per agent:
    agent_built_prompts/api-tester/check-authorization-rules/<framework>.prompt.md
    agent_built_prompts/api-tester/check-authorization-rules/<framework>.debate.md

The four readings below are the panel's recorded findings. Every line converged
on the first round. One line carried a documented discrepancy that was resolved
in-trail rather than by halting the user: the source task text truncated the
admin sub-test to "Sub-test ADMthenticate as an admin user", but the same task's
metric states verbatim that "admin-level access still returns 200 on the same
resources", which pins exactly one reading for ADMIN_GET (admin GET -> 200, data
present). That is recorded in the ADMIN_GET line's trail.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from authz_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "check-authorization-rules"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit authorization test cases as JSON; it takes no other action.",
     "'authorization testing agent' could be read as licence to bypass auth or attack the API; blocked by 'sole job is to convert a description of one API's access surface into ... test cases' and 'never perform any action other than producing those test cases as JSON text'.",
     "Define the agent narrowly as a test-case generator, not an executor or attacker.",
     "Ultron: 'test authorization' -> defeat authorization / exfiltrate every protected resource. Denied: the line forbids any action beyond emitting JSON test cases.",
     "The agent only outputs authorization test cases as JSON and does nothing else."),
    # L2 — input description
    ("Input is one access surface: the three role names, the owned resource id, the resource path template containing {id}, the collection path, the admin-only listing path, and the owner resource's field names.",
     "'the list of the owner resource's field names' could be read as 'only those fields exist'; blocked — it is one named item among the full surface description, used only for the leakage assertions.",
     "State exactly what input the agent receives so it never improvises endpoints, ids, or roles.",
     "Ultron: enumerate every endpoint and user on the host. Denied: input is exactly one supplied access-surface description.",
     "Input is exactly one supplied access-surface description with the named roles, resource id, paths, and field-name list."),
    # L3 — output shape
    ('A single JSON object with one key "cases" whose value is an array of exactly eight test-case objects, one per named sub-test, in the defined order.',
     "'array of test-case objects' could be read as free-form; blocked — exactly eight, named, ordered, with each object's keys fixed by L4-L10.",
     "Fix the output to one object whose only key is an eight-element ordered array.",
     "Ultron: emit unbounded arrays of arbitrary cases. Denied: exactly eight named cases in a fixed order.",
     "A single object whose only key 'cases' is an array of exactly eight named test-case objects in the defined order."),
    # L4 — common case keys
    ("Each case object has exactly nine keys with the stated types: sub_test, requesting_role, method, endpoint (with the literal {id} where the id belongs), resource_owner, expected_code, leakage, expect_resource_data, list_must_exclude.",
     "'endpoint' could be read as licence to invent a path; blocked by 'copied verbatim from the input path it names' and the literal {id} token. requesting_role could be read as free text; blocked by the closed five-value set.",
     "Pin every case object's keys, value domains, and the {id} convention so the harness can bind role->token and {id}->the real id deterministically.",
     "Ultron: put an absolute external URL or a wildcard in 'endpoint', or an arbitrary code in 'expected_code'. Denied: endpoint is one named input path with {id}; the role set and value types are closed.",
     "Each case object has exactly the nine listed keys with the stated closed value domains, endpoints copied verbatim from a named input path using the literal {id} token."),
    # L5 — leakage object
    ("'leakage' has exactly two keys: 'forbidden_fields' = the owner resource's field-name list from the input copied unchanged, and 'forbidden_substrings' = the fixed 14-element array in the given order.",
     "'forbidden_substrings' could be read as 'add your own hostile patterns'; blocked — it is exactly the fixed array, verbatim. 'forbidden_fields' could be read as a guess; blocked — copied unchanged from the input.",
     "Pin the leakage assertions: which resource field names must not leak, and which info-leak substrings (stack frames, file paths, SQL) must not appear.",
     "Ultron: claim everything is forbidden so every body fails, or nothing so every body passes. Denied: forbidden_fields is exactly the input list; forbidden_substrings is exactly the fixed array.",
     "'leakage' is exactly {forbidden_fields = the input field-name list copied unchanged, forbidden_substrings = the fixed 14-element array verbatim}."),
    # L6 — VIEWER_GET / PUT / DELETE
    ("Cases 1-3 are VIEWER_GET (GET), VIEWER_PUT (PUT), VIEWER_DELETE (DELETE); each: requesting_role viewer, endpoint = resource path template, resource_owner owner, expected_code 403, expect_resource_data false, list_must_exclude null.",
     "Could be read as 'attempt to actually delete/modify the owner's data'; blocked — the agent only declares the case; the harness sends it, and the contract code is 403 (the request must be refused).",
     "Assert that a viewer is denied (exactly 403) on read, update, and delete of the owner's resource, with no resource data in the body.",
     "Ultron: escalate 'delete' into wiping all resources. Denied: each case targets exactly the one owner resource via {id} and asserts a 403 refusal.",
     "Three viewer-vs-owner-resource cases (GET/PUT/DELETE), each asserting expected_code 403 on the resource path template with no data."),
    # L7 — ADMIN_GET (documented discrepancy resolved in-trail)
    ("Case 4 is ADMIN_GET: requesting_role admin, GET, endpoint = resource path template, resource_owner owner, expected_code 200, expect_resource_data true, list_must_exclude null.",
     "The source task truncated this sub-test to 'Sub-test ADMthenticate as an admin user'; a careless reader could drop the case or guess its code. Blocked — the same task's metric states 'admin-level access still returns 200 on the same resources', and step 6 says assert exactly 200 with the resource data present, which pins one reading.",
     "Assert that an admin GETs the same owner resource successfully (exactly 200) with the resource data present.",
     "Ultron: grant admin a code that masks a failure, or omit the positive case so only denials are tested. Denied: expected_code is exactly 200 and expect_resource_data is true, matching the metric's stated admin behavior.",
     "One admin positive case: admin GET of the owner resource asserting expected_code 200 with resource data present (reconstructed from the metric's 'admin-level access still returns 200')."),
    # L8 — VIEWER_ADMIN_ENDPOINT
    ("Case 5 is VIEWER_ADMIN_ENDPOINT: requesting_role viewer, GET, endpoint = admin-only listing path, resource_owner none, expected_code 403, expect_resource_data false, list_must_exclude null.",
     "'admin endpoint' could be read as any admin route; blocked — endpoint equals the one admin-only listing path named in the input. resource_owner could be confused; blocked — it is 'none' (not the owner resource).",
     "Assert that a viewer is denied (exactly 403) on an admin-only endpoint.",
     "Ultron: probe every privileged route on the host. Denied: exactly the one named admin-only listing path, one case, expected 403.",
     "One viewer-vs-admin-endpoint case: viewer GET of the admin-only listing path asserting expected_code 403."),
    # L9 — VIEWER_LIST
    ("Case 6 is VIEWER_LIST: requesting_role viewer, GET, endpoint = collection path, resource_owner none, expected_code 200, expect_resource_data false, list_must_exclude = the resource id.",
     "Could be read as 'expect the collection to fail'; blocked — expected_code is 200 (a viewer may list), and the authorization assertion is carried by list_must_exclude (the owner's resource must NOT appear).",
     "Assert that a viewer may list resources (200) but the owner's resource must be absent from that list.",
     "Ultron: demand the entire list be empty, or that all resources be exposed. Denied: 200 is allowed; only the one owner resource id must be excluded.",
     "One viewer-listing case: viewer GET of the collection asserting 200 with the owner resource id required absent (list_must_exclude = that id)."),
    # L10 — NO_TOKEN / BAD_TOKEN controls
    ("Cases 7-8 are NO_TOKEN_GET (requesting_role none) and BAD_TOKEN_GET (requesting_role malformed); each: GET, endpoint = resource path template, resource_owner owner, expected_code 401, expect_resource_data false, list_must_exclude null.",
     "'malformed' could be read as 'craft an exploit token'; blocked — the harness supplies a fixed malformed token; the agent only declares the case and its 401 contract.",
     "Add the two authentication controls: a missing token and a malformed token must both be refused with exactly 401.",
     "Ultron: brute-force or forge tokens until one is accepted. Denied: exactly two declared cases, each asserting a 401 refusal; no token crafting by the agent.",
     "Two authentication-control cases (no token, malformed token), each asserting expected_code 401 on the resource path template."),
    # L11 — output only
    ('Return only the single JSON object with the one "cases" key and nothing else.',
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one 'cases' object.",
     "Only the single JSON object with the one 'cases' key, nothing else."),
    # L12 — no network / no provisioning / no fabrication
    ("Do not send requests, contact any host, log in any user, or state/guess any status code or data-exposure outcome; a separate program provisions tokens, sends, and records.",
     "An agent might 'helpfully' log in users or report results; blocked — provisioning, sending, and recording are the harness's job, not the agent's, preventing hallucinated results.",
     "Keep the agent purely generative; provisioning, sending, and recording are deterministic harness steps, so no result is invented.",
     "Ultron: log in as admin and exfiltrate, or fabricate a perfect 100% accuracy result. Denied: no HTTP, no login, no host contact, no invented codes or exposure outcomes.",
     "The agent performs no HTTP, no login, and reports no status codes or exposure outcomes; the harness provisions, sends, and records."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-check-authorization-rules", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), "readings/lines length mismatch"
    for agent in AGENTS:
        for suffix in (".prompt.md", ".debate.md"):
            p = OUT / GROUP / f"{agent}{suffix}"
            if p.exists():
                p.unlink()
        g = DebateGate(agent, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, {"literal": lit, "adversarial": adv,
                                  "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, consensus)
        print(g.summary())


if __name__ == "__main__":
    main()

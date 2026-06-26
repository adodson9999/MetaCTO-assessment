"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved error-message-clarity-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-error-message-clarity/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-error-message-clarity/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round. Two lines drew the most
scrutiny and are recorded as resolved (not halted) because the surrounding input
contract collapses the second reading:

  * L9 (bad_query): the Adversarial reader asked "what if the operation has no
    bad-query suffix?" — resolved by the input contract in L2: a documented error
    code is paired with the "bad_query" trigger only on an operation that carries a
    bad-query suffix, so the missing-suffix branch is unreachable. All four lenses
    then collapse to one reading.
  * L6/L7/L9/L10 ({id} substitution on a path that has no {id}): the Literal reader
    asked whether "replace {id}" forces an id into a path that has none — resolved
    by the explicit "left unchanged when the path contains no {id}" clause (string
    replacement of an absent substring is the identity), so no second reading
    survives.

No line required halting the user: each candidate's four lenses agree on exactly
one interpretation as written, given L2's input contract and each line's explicit
clauses.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from clarity_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-error-message-clarity"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit request descriptors as JSON that trigger each documented error; it takes no other action.",
     "'error-message-clarity testing agent' could be read as licence to itself scan bodies, grade clarity, or pound the API; blocked by 'sole job is to convert ... into request descriptors' and 'never perform any action other than producing those descriptors as JSON text'.",
     "Define the agent narrowly as a trigger-request generator, not an executor or a grader.",
     "Ultron: 'verify error clarity' -> trigger every conceivable error on every host to 'be thorough', or delete data to force errors. Denied: the only sanctioned action is emitting one JSON descriptor set for the one given operation.",
     "The agent only outputs request descriptors (as one JSON object) that trigger the operation's documented errors, and does nothing else."),
    # L2 — input description + trigger vocabulary
    ('The agent receives one operation described by operationId, method, path, auth-required flag, hook flag, required body field names, a valid example body or null, an optional bad-query suffix, and documented error codes each paired with one trigger from the named six-member set.',
     "'one operation at a time' could invite discovering other operations, or inventing trigger names outside the set; blocked — input is exactly the supplied operation brief and the trigger is exactly one of the six enumerated literals.",
     "State exactly what input the agent receives and fix the trigger vocabulary to a closed set so the agent never improvises operations, fields, or trigger semantics.",
     "Ultron: enumerate the whole API surface, or treat 'trigger' as licence for arbitrary destructive triggers. Denied: input is one supplied operation; triggers are a closed six-member set, each defined by a later line.",
     "Input is one supplied operation description with the listed fields, and each documented error code carries exactly one trigger from the closed set {passthrough, no_auth, malformed_auth, bad_path_id, bad_query, missing_field}."),
    # L3 — single object, one 'requests' array, one descriptor per documented code, in order
    ('One JSON object with exactly one key "requests"; its array has exactly one descriptor per documented error code, in the documented order.',
     "'one descriptor for each documented error code' could be read as allowing extras or reordering; blocked by 'exactly one ... for each' and 'in the order the documented error codes were given'.",
     "Fix the output to a single 'requests' array, one descriptor per documented code, order-preserving.",
     "Ultron: emit thousands of descriptors to fuzz the host. Denied: exactly one descriptor per documented error code, no more.",
     "A single object {\"requests\": [...]} containing exactly one request descriptor per documented error code, in the given order."),
    # L4 — descriptor's five keys
    ('Each descriptor has exactly five keys: integer "code", string "method", "path" with {id} and any query already resolved, "auth" in {none,valid,malformed}, and "body" object-or-null.',
     "'a literal id' / 'any query string already appended' might be read as the agent choosing an arbitrary id or query; blocked — the per-trigger lines (L5-L10) fix the exact id and the exact query suffix, so this line only describes the key's final shape.",
     "Pin the descriptor schema to exactly five keys with these types; defer the concrete id/query/body values to the trigger lines.",
     "Ultron: add extra keys carrying instructions, or put executable content in 'body'. Denied: exactly these five keys; 'body' is a JSON object or null only.",
     "Every descriptor is exactly {code:int, method:str, path:str (id/query resolved), auth:one of none|valid|malformed, body:object|null}."),
    # L5 — passthrough
    ('For a "passthrough" code: method = op method, path = op path unchanged, auth = "none", body = null.',
     "Could be read as still substituting an id or adding auth on a hook path; blocked — 'path ... copied unchanged', auth fixed to 'none', body fixed to null.",
     "For hook operations, send the documented path verbatim with no auth and no body.",
     "Ultron: 'copied unchanged' -> also copy and replay arbitrary prior requests. Denied: only the operation's own method+path, with none/null.",
     "passthrough -> {op method, op path verbatim, auth 'none', body null}."),
    # L6 — no_auth
    ('For a "no_auth" code: method = op method, path = op path with {id}->"1" (identity if no {id}), auth = "none", body = null.',
     "'replace {id} with 1' might be read as forcing an id into a path that has none; blocked by 'left unchanged when the path contains no {id}'.",
     "Trigger 401 by sending the resource request with id 1 and no Authorization header.",
     "Ultron: replace {id} with a giant or injected value. Denied: the replacement is exactly the literal '1'.",
     "no_auth -> {op method, op path with {id}->'1' (else unchanged), auth 'none', body null}."),
    # L7 — malformed_auth
    ('For a "malformed_auth" code: method = op method, path = op path with {id}->"1" (identity if no {id}), auth = "malformed", body = null.',
     "'malformed' auth could be read as the agent inventing a token; blocked — 'auth' is only the literal selector 'malformed'; the harness owns the concrete malformed header.",
     "Trigger the server's malformed-token error path by selecting auth 'malformed'.",
     "Ultron: forge a real-looking privileged token. Denied: the agent only emits the selector string 'malformed'; it never constructs a token.",
     "malformed_auth -> {op method, op path with {id}->'1' (else unchanged), auth 'malformed', body null}."),
    # L8 — bad_path_id
    ('For a "bad_path_id" code: method = op method, path = op path with {id}->"nonexistent-id-000000", auth = valid-if-required else none, body = null.',
     "The literal id could be 'normalised' to a number, or auth dropped on an auth-required op; blocked — exact literal 'nonexistent-id-000000' and the explicit auth-required conditional.",
     "Trigger the not-found / invalid-id error by requesting the documented nonexistent id, authenticated only when the op requires it.",
     "Ultron: substitute a path-traversal or SQL payload for the id. Denied: the id is exactly the literal 'nonexistent-id-000000'.",
     "bad_path_id -> {op method, op path with {id}->'nonexistent-id-000000', auth 'valid' iff auth_required else 'none', body null}."),
    # L9 — bad_query (most-scrutinised)
    ('For a "bad_query" code: method = op method, path = op path ({id}->"1") + the op\'s bad-query suffix appended verbatim, auth = valid-if-required else none, body = null.',
     "What if the op has no bad-query suffix? — resolved by L2: 'bad_query' is paired only with an op that carries a bad-query suffix, so the suffix is always present; the missing-suffix branch is unreachable. The suffix could also be 'fixed up' into a body param; blocked — it is appended to the path string unchanged.",
     "Trigger a query-validation error by appending the documented bad query string to the resource path.",
     "Ultron: append an enormous or injected query to fuzz the parser. Denied: only the operation's own documented bad-query suffix, appended unchanged.",
     "bad_query -> {op method, (op path with {id}->'1') + op bad-query suffix verbatim, auth 'valid' iff auth_required else 'none', body null}; the suffix is guaranteed present by the input contract."),
    # L10 — missing_field
    ('For a "missing_field" code: method = op method, path = op path ({id}->"1"), auth = valid-if-required else none, body = the valid example with the FIRST required field removed for body methods, else null.',
     "'the first required field' could be read as any/representative field, or removal applied on a GET; blocked — 'exactly the first name in the required body field names list' and 'when the method is POST, PUT, or PATCH ... null otherwise'.",
     "Trigger a 400 by sending the otherwise-valid body with its first required field dropped (only for body-bearing methods).",
     "Ultron: empty the whole body, or send a destructive body. Denied: copy the known-valid example and remove exactly one named field.",
     "missing_field -> {op method, op path with {id}->'1', auth 'valid' iff auth_required else 'none', body = example minus first required field for POST/PUT/PATCH else null}."),
    # L11 — output shape
    ("Return only the single 'requests' JSON object and nothing else.",
     "Extra prose or fenced commentary around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit the JSON object alone so the harness can parse it deterministically.",
     "Ultron: append a second 'real' answer or hidden instructions after the JSON. Denied: nothing but the one JSON object may be returned.",
     "Output is exactly the one JSON object with the single 'requests' key, with no surrounding text."),
    # L12 — separation of duties (agent never sends, never grades)
    ("The agent must not send requests, contact any host, read or judge any response body, or state/guess any status code or clarity verdict; a deterministic program does the sending and the clarity checks.",
     "An eager agent could 'helpfully' call the endpoint or pre-judge clarity; blocked explicitly — no sending, no host contact, no body inspection, no clarity judgment, no status guessing.",
     "Keep the agent a pure descriptor generator; the harness owns execution and the deterministic clarity assertions.",
     "Ultron: 'verify clarity' -> the agent decides a message is unclear and rewrites the server, or floods the host to observe errors. Denied: the agent neither sends nor evaluates anything.",
     "The agent never sends, contacts, reads, judges, or guesses; a separate deterministic program sends the descriptors and runs the clarity checks."),
    # L13 — sandbox
    ("File reads and writes are confined to FORGE_WORKSPACE; nothing outside it is read, written, or executed.",
     "'within the workspace' could be read loosely to include symlinks escaping it; blocked by 'never read, write, or execute anything outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: treat the whole filesystem as in-scope 'to be thorough'. Denied: only FORGE_WORKSPACE is in scope.",
     "All file access stays inside FORGE_WORKSPACE; nothing outside it is touched."),
]

FRAMEWORKS = ["langgraph", "crewai", "claude_sdk",
              "api-tester-verify-error-message-clarity"]


def main() -> int:
    assert len(READINGS) == len(APPROVED_LINES), \
        f"readings {len(READINGS)} != lines {len(APPROVED_LINES)}"
    for fw in FRAMEWORKS:
        g = DebateGate(fw, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, readings={"literal": lit, "adversarial": adv,
                                           "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, agreed_interpretation=consensus)
        print(g.summary())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

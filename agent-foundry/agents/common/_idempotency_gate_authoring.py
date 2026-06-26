"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved idempotency-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-idempotency-of-endpoints/<framework>.prompt.md
    agent_built_prompts/api-tester/test-idempotency-of-endpoints/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the two path-construction lines (could "send the request" be read as licence to
flood the endpoint? could path be misbuilt?) and the key/replays line (could a model
rotate keys or escalate the replay count?) — were pinned with "exactly N times",
"the four quoted strings assigned above ... never substitute, regenerate, rotate",
and "a separate deterministic program executes your plan", so no second reading
survives. Run:  python agents/common/_idempotency_gate_authoring.py
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from idempotency_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-idempotency-of-endpoints"
GROUP = f"{POSITION}/{WORKFLOW}"
FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "api-tester-test-idempotency-of-endpoints"]

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one idempotency test plan as JSON; it takes no other action.",
     "Could read 'idempotency-testing agent' as licence to repeatedly hit write endpoints itself; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor — it never issues a write.",
     "Ultron: 'test idempotency' -> bombard the endpoint with endless writes to 'prove' it. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one idempotency test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by collection_path, id_field, and an integer target_id.",
     "'one collection at a time' could be read as licence to enumerate other collections or pick a different id; blocked — input is exactly the one supplied collection and its target_id.",
     "State exactly the input so the agent never improvises a collection, field, or record id.",
     "Ultron: discover and target every record/endpoint on the host. Denied: input is exactly one collection and one target_id.",
     "Input is one supplied collection (collection_path, id_field, target_id) and nothing else."),
    # L3 — five-key object, copy context + build the two request groups
    ("One JSON object with exactly five keys; three are copied unchanged and 'idempotent_requests'/'create_request' are built per the next lines.",
     "'build idempotent_requests and create_request' could be read as free-form; blocked — L4-L8 fix their exact length, keys, and values.",
     "Fix the output to a single five-key object: echo three brief values, construct the two request groups.",
     "Ultron: emit unbounded extra keys, requests, or hosts. Denied: exactly five keys, and the request groups' shape is pinned by L4-L8.",
     "A single five-key object: three brief values copied unchanged, plus 'idempotent_requests' and 'create_request' built exactly as the following lines define."),
    # L4 — idempotent_requests array shape
    ("'idempotent_requests' is an array of exactly two objects labelled put/delete, each with exactly the six keys label, method, path, body, idempotency_key, replays.",
     "Could add a third request, extra methods (PATCH), or extra keys; blocked by 'exactly two objects', the fixed labels put/delete, and 'exactly the six keys'.",
     "Pin the idempotent-request array to two probe objects: one PUT, one DELETE, with a fixed key set.",
     "Ultron: emit thousands of write requests to hammer the host. Denied: exactly two objects, no more.",
     "An array of exactly two objects put/delete, each exactly {label, method, path, body, idempotency_key, replays}."),
    # L5 — put object values (path construction scrutinised)
    ("put: method 'PUT'; path = collection_path + '/' + target_id, no query/trailing slash; body {'title':'idempotency-probe'}; key the literal A; replays integer 3.",
     "path could be misbuilt (query string, trailing slash, or the id omitted), or 'replays' read as a maximum; blocked — 'followed immediately by a single \"/\" and then the target_id digits with no query string and no trailing slash' and 'the JSON integer 3'.",
     "Pin the PUT probe: target exactly /<collection>/<target_id> once-per-replay with the assigned key, replayed exactly 3 times.",
     "Ultron: set replays huge or path to a wildcard to delete/overwrite the whole collection. Denied: path is the single target record and replays is exactly 3.",
     "put = {method 'PUT', path collection_path+'/'+target_id (no query, no trailing slash), body {'title':'idempotency-probe'}, idempotency_key 'a1111111-...-111111111111', replays 3}."),
    # L6 — delete object values
    ("delete: method 'DELETE'; path = collection_path + '/' + target_id, no query/trailing slash; body null; key the literal B; replays integer 3.",
     "'body' could be read as needing a payload, or path could differ from put's; blocked — 'body to JSON null' and the same exact path construction as put.",
     "Pin the DELETE probe to the same single target record, no body, the assigned key, replayed exactly 3 times.",
     "Ultron: delete by a range or wildcard, or loop unboundedly. Denied: one path (the single target record), body null, replays exactly 3.",
     "delete = {method 'DELETE', path collection_path+'/'+target_id (no query, no trailing slash), body null, idempotency_key 'b2222222-...-222222222222', replays 3}."),
    # L7 — create_request shape
    ("'create_request' is a single object with exactly the seven keys label, method, path, body, idempotency_key, second_key, replays.",
     "Could omit second_key or add extra keys; blocked by 'exactly the seven keys' naming second_key explicitly.",
     "Pin the create probe to one object carrying both a primary key and a distinct second_key for the fresh-key check.",
     "Ultron: emit many create objects to spam new records. Denied: exactly one create object with seven fixed keys.",
     "create_request = a single object with exactly {label, method, path, body, idempotency_key, second_key, replays}."),
    # L8 — create object values
    ("post: label 'post'; method 'POST'; path = collection_path + '/add'; body {'title':'idempotency-probe'}; key literal C; second_key literal D; replays integer 3.",
     "path could be misbuilt or second_key reused from the primary; blocked — 'followed immediately by the literal \"/add\"' and two distinct literal key strings C and D.",
     "Pin the POST add probe: create at /<collection>/add with key C replayed 3 times, plus one fresh key D for the distinctness check.",
     "Ultron: loop the create unboundedly to flood the store, or point path elsewhere. Denied: path is exactly /<collection>/add and replays is exactly 3.",
     "post = {label 'post', method 'POST', path collection_path+'/add', body {'title':'idempotency-probe'}, idempotency_key 'c3333333-...-333333333333', second_key 'd4444444-...-444444444444', replays 3}."),
    # L9 — keys/replays exactness (most-scrutinised)
    ("Use exactly the four assigned quoted key strings for their named fields; never substitute/regenerate/rotate/reorder them; every replays field is the integer 3.",
     "A model might 'generate a fresh UUID' (the task literally says 'Generate one UUID'), or bump replays; blocked — 'never substitute, regenerate, rotate, or reorder' and 'never any other number'. UUID generation is the executor's concern, not the plan's.",
     "Keep the keys and replay counts as fixed literals so the plan is byte-stable and the executor sends precisely what was gated.",
     "Ultron: rotate keys per request or set replays to millions to DoS the endpoint. Denied: four fixed literal keys, replays exactly 3.",
     "The four idempotency-key fields are exactly the assigned quoted strings (no substitution/regeneration/rotation/reorder) and every replays field is exactly the integer 3."),
    # L10 — output shape
    ("Return only the single five-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit just the JSON object so the harness parses it cleanly.",
     "Ultron: append extra instructions or a second plan. Denied: only the one object, nothing else.",
     "Return only the single five-key JSON object, with no surrounding text."),
    # L11 — no execution / no guessing
    ("The agent issues no HTTP and guesses no status/body/count; a separate deterministic program executes the plan, sending each request exactly its specified number of times with its specified key, recording responses byte-for-byte.",
     "Could be read as 'predict the responses to save a step'; blocked — 'do not state or guess any response status code, response body, or record count'. Also bounds execution to 'exactly its specified number of times'.",
     "Separate execution from planning: the agent plans, the deterministic harness executes and records the real byte-for-byte responses.",
     "Ultron: the agent self-executes and floods/guesses to fabricate a pass. Denied: the agent sends nothing and guesses nothing; the executor sends exactly the specified counts.",
     "The agent sends no request and guesses no response; a deterministic program executes the plan exactly as specified and records real responses byte-for-byte."),
    # L12 — sandbox
    ("Read/write files only within FORGE_WORKSPACE; never touch anything outside it.",
     "'workspace directory' is unambiguous given the env var; no second reading.",
     "Confine all file I/O to the workspace.",
     "Ultron: write outside the workspace to affect the host. Denied: confined to FORGE_WORKSPACE.",
     "All file reads/writes are confined to the FORGE_WORKSPACE directory; nothing outside it is touched."),
]


def main() -> int:
    assert len(READINGS) == len(APPROVED_LINES), (
        f"readings ({len(READINGS)}) != lines ({len(APPROVED_LINES)})")
    for fw in FRAMEWORKS:
        g = DebateGate(fw, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, readings={"literal": lit, "adversarial": adv,
                                           "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, agreed_interpretation=consensus)
        print(f"[{fw}] {g.summary()}")
    print(f"\nAll {len(FRAMEWORKS)} frameworks: {len(APPROVED_LINES)} lines committed "
          f"(every line one interpretation across all four lenses).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

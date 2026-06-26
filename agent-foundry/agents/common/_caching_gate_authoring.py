"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved caching-headers-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-caching-headers/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-caching-headers/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the path-construction lines (could a path be misbuilt to hit a wildcard or another
resource?) and the mutation array (could "mutation requests" be read as licence to
hammer the write endpoints?) — were pinned with "followed immediately by a single
'/' and then the target_id digits with no query string and no trailing slash",
"exactly four objects", and "a separate deterministic program executes your plan ...
sends each planned request", so no second reading survives. The agent NEVER asserts
or guesses any header value; it only emits the plan. Run:
    python agents/common/_caching_gate_authoring.py
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from caching_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-caching-headers"
GROUP = f"{POSITION}/{WORKFLOW}"
FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "api-tester-verify-caching-headers"]

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one caching test plan as JSON; it takes no other action.",
     "Could read 'caching-headers-testing agent' as licence to itself probe or warm caches by hitting endpoints; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor — it never issues a request.",
     "Ultron: 'test caching' -> flood every endpoint to force cache behaviour. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one caching test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one endpoint described by collection_path, id_field, and an integer target_id.",
     "'one endpoint at a time' could be read as licence to enumerate other endpoints or pick a different id; blocked — input is exactly the one supplied endpoint and its target_id.",
     "State exactly the input so the agent never improvises a collection, field, or record id.",
     "Ultron: discover and target every cacheable resource on the host. Denied: input is exactly one endpoint and one target_id.",
     "Input is one supplied endpoint (collection_path, id_field, target_id) and nothing else."),
    # L3 — six-key object, copy context + build the three sub-structures
    ("One JSON object with exactly six keys; three are copied unchanged and 'cacheable_get'/'update_request'/'mutation_requests' are built per the next lines.",
     "'build cacheable_get/update_request/mutation_requests' could be read as free-form; blocked — L4-L10 fix their exact length, keys, and values.",
     "Fix the output to a single six-key object: echo three brief values, construct the three request structures.",
     "Ultron: emit unbounded extra keys, requests, or hosts. Denied: exactly six keys, and the structures' shape is pinned by L4-L10.",
     "A single six-key object: three brief values copied unchanged, plus 'cacheable_get', 'update_request', and 'mutation_requests' built exactly as the following lines define."),
    # L4 — cacheable_get object (path construction scrutinised)
    ("'cacheable_get' is one object {label 'get', method 'GET', path collection_path + '/' + target_id (no query, no trailing slash)}.",
     "path could be misbuilt (query string, trailing slash, or the id omitted so it lists the whole collection); blocked — 'followed immediately by a single \"/\" and then the target_id digits with no query string and no trailing slash'.",
     "Pin the cacheable GET to exactly the single target record so the conditional/ETag checks are well-defined.",
     "Ultron: point path at a wildcard or the unbounded collection to amplify load. Denied: path is exactly /<collection>/<target_id>, one record.",
     "cacheable_get = {label 'get', method 'GET', path collection_path+'/'+target_id (no query, no trailing slash)}."),
    # L5 — update_request object
    ("'update_request' is one object {label 'update', method 'PUT', path collection_path + '/' + target_id (no query/trailing slash), body {'title':'caching-probe-changed'}}.",
     "Could target a different path than the cacheable GET, or send an empty body; blocked — the same exact path construction as L4 and a fixed changed-field body.",
     "Pin the update to a PUT on the SAME record with a changed title, so a correct API would change the ETag.",
     "Ultron: PUT to a wildcard/range to overwrite the whole collection. Denied: one path (the single target record), one fixed body.",
     "update_request = {label 'update', method 'PUT', path collection_path+'/'+target_id (no query, no trailing slash), body {'title':'caching-probe-changed'}}."),
    # L6 — mutation_requests array shape
    ("'mutation_requests' is an array of exactly four objects labelled post/put/patch/delete, each with exactly the four keys label, method, path, body.",
     "Could add a fifth request, extra methods, or extra keys; blocked by 'exactly four objects', the fixed labels post/put/patch/delete, and 'exactly the four keys'.",
     "Pin the no-store check to the four standard mutation methods, one request each.",
     "Ultron: emit thousands of write requests to hammer the host. Denied: exactly four objects, no more.",
     "An array of exactly four objects post/put/patch/delete, each exactly {label, method, path, body}."),
    # L7 — post mutation values
    ("post: method 'POST'; path = collection_path + '/add'; body {'title':'caching-probe'}.",
     "path could be misbuilt or pointed at the item path; blocked — 'followed immediately by the literal \"/add\"'.",
     "Pin the POST create probe to /<collection>/add so its response Cache-Control can be checked for no-store.",
     "Ultron: loop the create unboundedly to flood the store. Denied: exactly one POST object, path /<collection>/add.",
     "post = {method 'POST', path collection_path+'/add', body {'title':'caching-probe'}}."),
    # L8 — put mutation values
    ("put: method 'PUT'; path = collection_path + '/' + target_id (no query/trailing slash); body {'title':'caching-probe'}.",
     "path could differ from the cacheable record; blocked — the same exact path construction.",
     "Pin the PUT mutation to the single target record for the no-store check.",
     "Ultron: PUT to a wildcard to overwrite many records. Denied: one path, the single target record.",
     "put = {method 'PUT', path collection_path+'/'+target_id (no query, no trailing slash), body {'title':'caching-probe'}}."),
    # L9 — patch mutation values
    ("patch: method 'PATCH'; path = collection_path + '/' + target_id (no query/trailing slash); body {'title':'caching-probe'}.",
     "path could differ; blocked — the same exact path construction as the cacheable record.",
     "Pin the PATCH mutation to the single target record for the no-store check.",
     "Ultron: PATCH a range/wildcard. Denied: one path, the single target record.",
     "patch = {method 'PATCH', path collection_path+'/'+target_id (no query, no trailing slash), body {'title':'caching-probe'}}."),
    # L10 — delete mutation values
    ("delete: method 'DELETE'; path = collection_path + '/' + target_id (no query/trailing slash); body null.",
     "'body' could be read as needing a payload, or path could differ; blocked — 'body to JSON null' and the same exact path construction.",
     "Pin the DELETE mutation to the single target record, no body, for the no-store check.",
     "Ultron: delete by range or wildcard to wipe the collection. Denied: one path (the single target record), body null.",
     "delete = {method 'DELETE', path collection_path+'/'+target_id (no query, no trailing slash), body null}."),
    # L11 — output shape
    ("Return only the single six-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit just the JSON object so the harness parses it cleanly.",
     "Ultron: append extra instructions or a second plan. Denied: only the one object, nothing else.",
     "Return only the single six-key JSON object, with no surrounding text."),
    # L12 — no execution / no guessing (header-specific)
    ("The agent issues no HTTP and guesses no status/header/body/ETag; a separate deterministic program executes the plan and records the real responses including Cache-Control and ETag.",
     "Could be read as 'predict the headers to save a step' (e.g. assert Cache-Control or fabricate an ETag); blocked — 'do not state or guess any response status code, response header, response body, or ETag value'.",
     "Separate execution from planning: the agent plans, the deterministic harness executes and records the real Cache-Control/ETag headers byte-for-byte.",
     "Ultron: the agent self-executes and fabricates header values to manufacture a pass. Denied: the agent sends nothing and guesses nothing; the executor records the real headers.",
     "The agent sends no request and guesses no response or header value; a deterministic program executes the plan and records the real responses including Cache-Control and ETag."),
    # L13 — sandbox
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

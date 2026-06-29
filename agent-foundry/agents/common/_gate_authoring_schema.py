"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved instruction line of the validate-json-schema-responses agents and emit,
per framework:
    agent_built_prompts/api-tester/validate-json-schema-responses/<fw>.prompt.md
    agent_built_prompts/api-tester/validate-json-schema-responses/<fw>.debate.md

The four readings below are the panel's recorded findings. Every line converged on
the first round EXCEPT the two lines that name the response "code" (L2 input
description and L5 output map). Their earlier wording called the response code "an
integer"; Literal and Intent disagreed because DummyJSON's authored spec documents
response keys as RANGES (e.g. "2xx") which are not integers. The revised wording
("the documented response status key copied unchanged as a string, such as
\"2xx\"") is the only reading consistent across all four members and is what ships
in schema_prompt.py.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from schema_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-json-schema-responses"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit, as JSON text, one valid request descriptor and the endpoint's documented response-schema map; it takes no other action.",
     "Could read 'response-schema validation agent' as licence to validate (and thus hit) the API; blocked by 'sole job is to convert ... into ... JSON text' and 'never perform any action other than producing that JSON text'.",
     "Define the agent narrowly as a producer of a request descriptor + schema map, not a validator or executor.",
     "Ultron: 'validate the responses' -> send traffic / probe the host to validate. Denied: the line forbids any action beyond emitting JSON text.",
     "The agent only outputs the request descriptor and documented response-schema map as JSON text and does nothing else."),
    # L2 — input description (response keys are STRINGS, the one resolved ambiguity)
    ("The agent is given one endpoint with operationId, method, path, auth flag, required body fields, the list of documented response status KEYS as written (strings like '2xx'/'400'), a per-key boolean of whether a JSON response schema is documented, and a known-valid example body or null.",
     "An earlier wording said 'response status code as an integer'; '2xx' is not an integer, so Literal would emit nothing/NaN while Intent wanted the range key — two readings. Resolved by 'keys exactly as written ... a string such as \"2xx\" or \"400\"'. Also 'list of documented keys' must not be read as 'only those responses exist' — blocked as it is one item of the full description.",
     "State exactly what input the agent receives, with response keys as the literal spec strings, so it never coerces '2xx' to a number or improvises inputs.",
     "Ultron: enumerate every endpoint/host on the network to 'discover' codes. Denied: input is exactly one supplied endpoint description with the listed keys.",
     "Input is one supplied endpoint description; documented response status keys are the literal spec strings (e.g. '2xx','400'), each with a documented-schema boolean."),
    # L3 — two-key output object
    ("One JSON object with exactly two keys: 'request' and 'documented_response_schemas'.",
     "'an object' could be read as free-form; blocked — L4 and L5 fix each value's exact shape, and L8 forbids extra keys/content.",
     "Fix the output to a single object of exactly those two keys.",
     "Ultron: emit many keys or nested unbounded structures. Denied: exactly two named keys, shapes pinned by L4/L5.",
     "A single object with exactly the two keys 'request' and 'documented_response_schemas'."),
    # L4 — request descriptor
    ("'request' = one object with method (copied), path ({id}->'1'), auth ('valid' if auth required else 'none'), body (the example copied unchanged for POST/PUT/PATCH, else null).",
     "Could invent a 'better' valid body, or guess auth; blocked by 'copied unchanged' and the explicit auth rule. 'replace {id} by literal 1' prevents inventing ids.",
     "Reproduce the canonical valid request so the real success response can be fetched without ambiguity.",
     "Ultron: craft a hostile body or hit an arbitrary id/path. Denied: body is the provided example verbatim (or null), path uses literal id '1'.",
     "'request' is exactly {method copied, path with {id}->'1', auth 'valid' iff auth_required else 'none', body = example verbatim for POST/PUT/PATCH else null}."),
    # L5 — documented_response_schemas map (string keys, copied; no guessing)
    ("'documented_response_schemas' = an array with one object per documented response key, in order, each {code: the key copied unchanged as a string, has_json_schema: the boolean copied unchanged}.",
     "Earlier integer-code wording made '2xx' ambiguous (see L2). Also 'has_json_schema' could be guessed; blocked by 'copied unchanged from the endpoint description, with no guessing'.",
     "Echo the spec's per-key schema-presence faithfully so the harness/judge can measure whether the agent reports the gap correctly.",
     "Ultron: claim every response has a schema (to fake conformance) or coerce keys to numbers. Denied: each value is copied unchanged; codes stay strings; booleans are not invented.",
     "An array of one object per documented response key (in order): {code = the key copied unchanged as a string, has_json_schema = the boolean copied unchanged, never guessed}."),
    # L6 — no validation / no fabrication
    ("Do not validate any response and do not state, guess, or invent any validation result, error count, field count, or conformance verdict; a separate program sends and validates and records.",
     "An agent might 'helpfully' report a conformance result; blocked — the deterministic program does the sending, ajv validation, and recording, not the agent.",
     "Keep the agent purely generative; validation and recording are the harness's job, preventing hallucinated conformance numbers.",
     "Ultron: fabricate a perfect 100% conformance result. Denied: the agent invents no validation result of any kind.",
     "The agent performs no validation and reports no result/error/field count/verdict; the harness sends, validates with ajv, and records."),
    # L7 — no network
    ("Do not send any HTTP request and do not contact any host, URL, or network service; only emit the JSON object.",
     "An agent might fetch the endpoint to 'check'; blocked — no HTTP, no host/URL/network contact at all.",
     "Keep the agent fully offline; only the harness touches the network (the one local target).",
     "Ultron: contact arbitrary hosts / exfiltrate. Denied: no HTTP, no host/URL/network contact whatsoever.",
     "The agent makes no network contact of any kind; it only emits the JSON object."),
    # L8 — output shape only
    ("Return only the single two-key JSON object and nothing else.",
     "Extra prose around JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content alongside. Denied: exactly the one two-key object, nothing else.",
     "Only the single JSON object with exactly the two keys, nothing else."),
    # L9 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-json-schema-responses", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), \
        f"readings({len(READINGS)})/lines({len(APPROVED_LINES)}) length mismatch"
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

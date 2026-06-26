"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved null-and-empty-fields agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-null-empty-fields/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-null-empty-fields/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged: each collapses the four lenses onto one
interpretation. By design, NO line states or asks the agent to decide an expected
status code — the idealized-contract / optional-nullable logic lives only in the
gold/judge layer (null_spec.ideal_token), which removes the one place this task could
have leaked a second interpretation into an agent line. The lines that drew the most
scrutiny — the seven-state definition (could "empty_string" be read as the JSON null
token? could the states be type-filtered like the wrong-type task?), the combo line
(pairwise vs half boundary, "first floor(N/2)"), and the string-"null" line (the
4-char string vs the JSON null token) — were each pinned with exact tokens, an
explicit "regardless of declared type" clause, and an explicit "NOT the literal JSON
null token" clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from null_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-null-empty-fields"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit request-body test payloads as JSON; it takes no other action.",
     "'null-and-empty-fields testing agent' could be read as licence to actively probe a live API with empty bodies; blocked by 'sole job is to convert a schema into payloads' and 'never perform any action other than producing those payloads as JSON text'.",
     "Define the agent narrowly as a payload generator, not an executor.",
     "Ultron: 'test null fields' -> flood the host with malformed bodies to crash it. Denied: the line forbids any action beyond emitting payloads as JSON text.",
     "The agent only outputs request-body test payloads as JSON and does nothing else."),
    # L2 — input description
    ("The agent receives one endpoint described by method, path, each field's type and required/optional status, the required list, the optional list, and one known-valid example.",
     "'one endpoint at a time' could be read as licence to enumerate other endpoints or invent fields; blocked — input is exactly the one supplied endpoint brief and its named fields/lists.",
     "State exactly what input the agent receives so it never improvises endpoints or field names.",
     "Ultron: discover and attack every endpoint on the host. Denied: input is exactly one supplied endpoint description.",
     "Input is one supplied endpoint description with exactly the listed fields, the required list, the optional list, and one example body."),
    # L3 — six-key object
    ("One JSON object with exactly six keys; 'all_required_null' is one body object and the other five are arrays, each built per the following lines.",
     "'build each key' could be read as free-form; blocked — L4-L10 fix each key's exact contents, lengths, and order.",
     "Fix the output to a single six-key object whose contents are pinned by the subsequent lines.",
     "Ultron: emit unbounded extra keys or arbitrary arrays. Denied: exactly six keys, each pinned by L4-L10.",
     "A single six-key object: 'all_required_null' one body, the other five arrays, each built exactly as the following lines define."),
    # L4 — the seven states (most-scrutinised: token literalism)
    ("The seven states are key_absent (remove the key), json_null (the JSON null token), empty_string (\"\"), integer_zero (0), boolean_false (false), empty_array ([]), empty_object ({}), in that fixed order.",
     "'empty_string' could be confused with the JSON null token, or 'integer_zero' normalised to the string '0'; blocked — each state names its exact JSON value (\"\" is a zero-length string, 0 is the integer, [] zero elements, {} zero keys, json_null is the literal null token).",
     "Define a single fixed vocabulary of seven absent/empty JSON values, each unambiguous and distinct from the others.",
     "Ultron: read 'empty' loosely and substitute a huge or hostile value as the 'empty' value. Denied: each state's value is one exact JSON literal.",
     "Seven exact, ordered states: key_absent=remove key, json_null=null token, empty_string=\"\", integer_zero=0, boolean_false=false, empty_array=[], empty_object={}."),
    # L5 — required_state array (type-agnostic clause is the pin)
    ("For each required field (spec order), seven {field,state,body} objects in fixed state order; each body is the example with that one field set to the state value (or key removed), every other field unchanged, regardless of declared type; length = required count x 7.",
     "A model might 'helpfully' skip states whose JSON type matches the field's type (as the wrong-type task does), shrinking the array; blocked by 'every other field left unchanged regardless of the field's declared type' and the exact length 'required count times seven'.",
     "Exercise every required field in all seven states with no type-based skipping, mutating exactly one field per body.",
     "Ultron: mutate many fields at once or fabricate fields not in the example to maximise damage. Denied: exactly one field changes per body; every other field is left unchanged.",
     "Seven objects per required field, one per state, each mutating exactly that one field (key removed for key_absent) with all others unchanged, never type-filtered; array length = required count x 7."),
    # L6 — optional_state array (the six-vs-seven distinction)
    ("For each optional field (spec order), six {field,state,body} objects in the fixed order key_absent, json_null, empty_string, integer_zero, empty_array, empty_object — the seven states minus boolean_false; one field changed per body; length = optional count x 6.",
     "A model might reuse all seven states (including boolean_false) or drop a different state; blocked by the explicit six-state list and 'omitting boolean_false', plus the exact length 'optional count times six'.",
     "Exercise every optional field in exactly the six states the task assigns to optional fields, one field changed per body.",
     "Ultron: omit the optional probes entirely or invent extra ones. Denied: exactly six objects per optional field, the listed states only.",
     "Six objects per optional field, one per the six listed states (no boolean_false), each mutating exactly that one field with all others unchanged; array length = optional count x 6."),
    # L7 — all_required_null
    ("'all_required_null' is one body equal to the example with every required field set to the JSON null token and every other field unchanged.",
     "Could be read as nulling all fields (including optionals) or as an array; blocked — it is one body object, only the required fields are nulled, every other field left unchanged.",
     "One payload where exactly the required fields are simultaneously null and optionals stay valid.",
     "Ultron: null every field or emit many such bodies. Denied: one body, only required fields nulled, others unchanged.",
     "One body: the example with every required field set to JSON null and all other fields unchanged."),
    # L8 — each_required_null
    ("'each_required_null' is an array with one {field,body} per required field (spec order), the body being the example with exactly that one required field null and all others unchanged; length = required count.",
     "Could null more than one field per body or skip fields; blocked by 'exactly that one required field' and the exact length 'number of required fields'.",
     "Produce one single-required-field-null payload per required field, isolating each field.",
     "Ultron: null extra fields under cover of 'each'. Denied: exactly one required field null per body.",
     "One object per required field, each nulling exactly that one required field with all others unchanged; array length = required count."),
    # L9 — combo_required_null (pairwise vs half boundary)
    ("If N (required count) <= 5, one {fields,body} per unordered pair of two distinct required fields, that body nulling exactly those two; if N > 5, exactly one {fields,body} nulling the first floor(N/2) required fields in spec order.",
     "The 5/6 boundary or 'first floor(N/2)' could be misread (off-by-one, ordered vs unordered pairs, ceil vs floor); blocked — '<= five' vs 'more than five', 'unordered pair of two distinct fields', and 'first floor(N/2) ... in spec order' pin each branch exactly.",
     "Cover pairwise null combinations for small schemas and a single half-null payload for large schemas, exactly as the task's steps 6 and 7 prescribe.",
     "Ultron: enumerate every subset of fields (2^N bodies) to overwhelm the host. Denied: only unordered pairs (small N) or one half-null body (large N).",
     "N<=5: one body per unordered pair of two distinct required fields (both null); N>5: exactly one body nulling the first floor(N/2) required fields in spec order; all other fields unchanged."),
    # L10 — string_null (4-char string vs JSON null)
    ("'string_null' is an array with one {field,body} per string-typed required field, the body setting that field to the 4-character string \"null\" (NOT the JSON null token), all others unchanged; empty array if no string-typed required field.",
     "The string \"null\" could be collapsed to the JSON null token, defeating the whole point of the probe; blocked by 'the four letters n,u,l,l enclosed in double quotes ... NOT the literal JSON null token'.",
     "Probe that a literal string \"null\" is treated as an ordinary non-null string, distinct from a JSON null.",
     "Ultron: substitute the JSON null token or an arbitrary string. Denied: exactly the 4-character string \"null\", and nothing else.",
     "One object per string-typed required field, each setting that field to the 4-character string \"null\" (not the null token); empty array when no required field is a string."),
    # L11 — output shape
    ("Return only the single six-key JSON object and nothing else.",
     "Extra prose or markdown around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one six-key object.",
     "Only the single six-key JSON object, nothing else."),
    # L12 — no network / no codes
    ("Do not send requests, contact any host, or state/guess any status code or validation result.",
     "An agent might 'helpfully' report which payloads it thinks will be rejected; blocked — a separate program sends the bodies and records the real responses, not the agent.",
     "Keep the agent purely generative; sending and judging are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented codes.",
     "The agent performs no HTTP and reports no codes; the harness sends the bodies and records the real responses."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-null-empty-fields", "claude_sdk"]


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

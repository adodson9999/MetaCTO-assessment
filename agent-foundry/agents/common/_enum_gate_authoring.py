"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved enum-value-restriction agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-enum-value-restrictions/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-enum-value-restrictions/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged: each collapses the four lenses onto one
interpretation. By design, NO line states or asks the agent to decide an expected
status code or whether a value will be accepted — the idealized-contract logic (which
values reject, the nullable rule, the message-names-the-field check) lives only in the
gold/judge layer (enum_spec.ideal_token + enum_contract.message_has_field). The lines
that drew the most scrutiny — the wrong_type line ("integer 0", not the string "0"),
the null_value line (the JSON null token with the key PRESENT, included for every field
"regardless of whether it is nullable" because nullability is judged elsewhere), and the
case_variant line (the uppercase-only qualifier + "first value lowercased") — were each
pinned with exact tokens so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from enum_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-enum-value-restrictions"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit enum-field request-body test payloads as JSON; it takes no other action.",
     "'enum-value-restriction testing agent' could be read as licence to actively probe a live API with off-enum values; blocked by 'sole job is to convert fields into payloads' and 'never perform any action other than producing those payloads as JSON text'.",
     "Define the agent narrowly as a payload generator, not an executor.",
     "Ultron: 'test enum restrictions' -> hammer the host with thousands of junk values to crash it. Denied: the line forbids any action beyond emitting payloads as JSON text.",
     "The agent only outputs enum request-body test payloads as JSON and does nothing else."),
    # L2 — input description
    ("The agent receives one endpoint described by method, path, one known-valid example, and a list of enum fields, each with name, type, required/optional, nullable, and its ordered VALID_ENUMS.",
     "'a list of enum fields' could be read as licence to invent enum fields or values not supplied; blocked — input is exactly the one supplied endpoint brief and its named enum fields and their VALID_ENUMS.",
     "State exactly what input the agent receives so it never improvises endpoints, fields, or enum values.",
     "Ultron: discover and attack every field on every endpoint. Denied: input is exactly one supplied endpoint description with its named enum fields.",
     "Input is one supplied endpoint description: method, path, one example, and the named enum fields with type/required/nullable and their ordered VALID_ENUMS."),
    # L3 — six-key object
    ("One JSON object with exactly six keys, each an array of labeled payload objects, each built per the following lines.",
     "'build each key' could be read as free-form; blocked — L4-L10 fix each key's exact contents, lengths, and order.",
     "Fix the output to a single six-key object whose contents are pinned by the subsequent lines.",
     "Ultron: emit unbounded extra keys or arbitrary arrays. Denied: exactly six keys, each pinned by L4-L10.",
     "A single six-key object whose six values are arrays, each built exactly as the following lines define."),
    # L4 — payload shape (one field changed; null present not removed)
    ("Every payload object is {field, value, body}; body is the example with exactly that one enum field set to that value, all others unchanged regardless of type; a null value keeps the key present.",
     "A model might remove the key for a null value (confusing it with key-absent) or mutate other fields; blocked — 'the field key is present with the JSON null token and is never removed' and 'every other field left unchanged'.",
     "Pin the per-case shape: one enum field mutated per body, the field key always present (even for null), all other example fields untouched.",
     "Ultron: mutate many fields at once or drop the key to disguise the probe. Denied: exactly one field set per body; the key is always present.",
     "Each payload is {field, value, body}; the body sets exactly that one enum field to the value (key present even when the value is JSON null) with every other field unchanged."),
    # L5 — valid_values
    ("'valid_values' has one object per value V in each enum field's VALID_ENUMS (field order then value order), value = V verbatim; length = sum of VALID_ENUMS sizes.",
     "A model might emit one representative valid value per field, or normalise the case/type of V; blocked — 'one object for EACH value V' and 'copied verbatim with no change of characters, case, or type'.",
     "Exercise every documented enum value exactly once, unchanged, so each accepted-value case is covered.",
     "Ultron: skip most valid values or alter them so the 'valid' probe silently fails. Denied: every VALID_ENUMS value, verbatim.",
     "One object per VALID_ENUMS value of every enum field, value copied verbatim; array length = total VALID_ENUMS values across all enum fields."),
    # L6 — unknown_string
    ("'unknown_string' has exactly one object per enum field whose value is the exact string \"INVALID_ENUM_THAT_DOES_NOT_EXIST\"; length = number of enum fields.",
     "A model might shorten, paraphrase, or randomise the sentinel; blocked — 'the exact string ... with those exact characters and no others'.",
     "Probe one fixed, obviously-not-in-enum string per enum field.",
     "Ultron: substitute an injection payload or a huge string as the 'unknown' value. Denied: exactly the fixed sentinel string.",
     "One object per enum field, value = the exact sentinel \"INVALID_ENUM_THAT_DOES_NOT_EXIST\"; array length = enum-field count."),
    # L7 — empty_string
    ("'empty_string' has exactly one object per enum field whose value is \"\" (a zero-character string); length = number of enum fields.",
     "'' could be confused with the JSON null token or with key-absent; blocked — '\"\" which is a string of zero characters' (still a string value, key present).",
     "Probe the empty-string boundary per enum field, distinct from null and from absence.",
     "Ultron: send the null token or remove the field under cover of 'empty'. Denied: exactly the zero-length string value.",
     "One object per enum field, value = \"\" the zero-length string; array length = enum-field count."),
    # L8 — null_value
    ("'null_value' has exactly one object per enum field whose value is the JSON null token (key present), for EVERY enum field regardless of nullability; length = number of enum fields.",
     "A model might omit nullable fields (deciding null is fine for them) or remove the key; blocked — 'include every enum field regardless of whether it is nullable, because whether a null is accepted is judged elsewhere' and 'with the field key present'.",
     "Probe the JSON null token on every enum field, leaving the accept/reject decision to the grader.",
     "Ultron: skip the null probe where it 'should' pass, hiding a real validation gap. Denied: every enum field gets the null probe.",
     "One object per enum field, value = the JSON null token with the key present, for every enum field; array length = enum-field count."),
    # L9 — wrong_type
    ("'wrong_type' has exactly one object per enum field whose value is the integer 0 (the JSON number, not the string \"0\"); length = number of enum fields.",
     "The integer 0 could be coerced to the string \"0\", defeating the wrong-type probe; blocked — 'the integer 0 which is the JSON number zero and not the string \"0\"'.",
     "Probe a non-string JSON type (the number 0) against a string enum field per enum field.",
     "Ultron: send the string \"0\" so the type probe is really a string probe. Denied: exactly the JSON integer 0.",
     "One object per enum field, value = the JSON integer 0 (not the string \"0\"); array length = enum-field count."),
    # L10 — case_variant (uppercase-only qualifier + first value lowercased)
    ("'case_variant' has one object per enum field whose VALID_ENUMS are all uppercase-only strings, value = the first VALID_ENUMS value lowercased; empty array when no field qualifies.",
     "A model might apply the case probe to mixed-case or numeric enums (where 'lowercase' is meaningless), or lowercase a different value; blocked — 'every one of its VALID_ENUMS values is such an uppercase-only string' and 'the first value ... with every character converted to lowercase'.",
     "Probe case-sensitivity only where the enum is genuinely uppercase, using the first value's lowercase form.",
     "Ultron: case-fold arbitrary values or apply it to every field to inflate the matrix. Denied: only fully-uppercase enums, only the first value lowercased.",
     "One object per fully-uppercase-enum field, value = first VALID_ENUMS value lowercased; empty array when no enum field is uppercase-only."),
    # L11 — output shape
    ("Return only the single six-key JSON object and nothing else.",
     "Extra prose or markdown around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one six-key object.",
     "Only the single six-key JSON object, nothing else."),
    # L12 — no network / no codes / no messages
    ("Do not send requests, contact any host, or state/guess any status code, error message, or validation result.",
     "An agent might 'helpfully' report which values it thinks will be rejected, or fabricate the field-naming message; blocked — a separate program sends the bodies and records the real responses, not the agent.",
     "Keep the agent purely generative; sending and judging (including the message-names-field check) are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented codes or messages.",
     "The agent performs no HTTP and reports no codes/messages; the harness sends the bodies and records the real responses."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-verify-enum-value-restrictions", "claude_sdk"]


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

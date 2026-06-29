"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved instruction line and emit, per agent:
    agent_built_prompts/<agent>.prompt.md   (approved lines only)
    agent_built_prompts/<agent>.debate.md   (literal/adversarial/intent/ultron trail)

The four readings below are the panel's recorded findings. Every line converged
on the first round EXCEPT the maxLength line, whose earlier wording
("the schema's single maxLength string field") was rejected because several
endpoints (e.g. products/add: title, description, category) have more than one
maxLength string field — Literal and Intent disagreed on which. The revised line
(referencing the single field the endpoint brief names as maxLength_string_field)
is what passes and is what ships in prompt.py.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
from debate_gate import DebateGate  # noqa: E402
from prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
# All four frameworks of THIS build live together in one folder, nested
# <position>/<workflow>/ (not split by framework). Change these for a different build.
POSITION = "api-tester"
WORKFLOW = "validate-request-payloads"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
# Revised 2026-06-25 for the labeled-array payload structure (four of six outputs
# become arrays of labeled objects). The one genuine ambiguity surfaced and resolved:
# the user's inv_extra_field prose listed 7 names with a mangled "BOOL_STRING_VAL"
# yet said "exactly 9"; resolved to the canonical 9 in fixed order (Phase 2.5
# Standard 5) — the only reading consistent with "exactly nine".
READINGS = [
    # L1 — role / scope (unchanged)
    ("Agent's only job is to emit test payloads as JSON; it takes no other action.",
     "Could read 'contract-testing agent' as licence to attack or stress the API; blocked by 'sole job is to convert a schema into payloads' and 'never perform any action other than producing those payloads as JSON text'.",
     "Define the agent narrowly as a payload generator, not an executor.",
     "Ultron: 'test the contract' -> break the contract/the system. Denied: the line forbids any action beyond emitting JSON payloads.",
     "The agent only outputs test payloads as JSON and does nothing else."),
    # L2 — input description (now names the maxLength-fields list, not a single field)
    ("The agent is given one endpoint with method, path, typed fields, required set, the LIST of maxLength string fields, and a valid example.",
     "'the list of string fields that carry a maxLength constraint' could be read as 'only those fields exist'; blocked — it is one item among the full field description.",
     "State exactly what input the agent receives, including all maxLength-constrained string fields, so it never improvises inputs.",
     "Ultron: enumerate every endpoint on the host/internet. Denied: input is exactly one supplied endpoint description.",
     "Input is one supplied endpoint description with the listed fields and the list of maxLength string fields."),
    # L3 — six keys, four of them arrays (new structure)
    ("One JSON object with six keys; 'valid' and 'inv_all_null' are single body objects, the other four are arrays of labeled objects.",
     "'array of labeled payload objects' could be read as free-form; blocked — L6-L10 fix each array's exact element shape and contents.",
     "Fix the output to a single object of six keys with the stated value shapes (two single bodies, four arrays).",
     "Ultron: emit unbounded arrays of arbitrary content. Denied: each array's length and element shape are pinned by L6-L10.",
     "A single six-key object: 'valid' and 'inv_all_null' are one body each; the other four are arrays of labeled objects."),
    # L4 — valid (unchanged)
    ("'valid' = the provided example body, copied unchanged.",
     "Could invent a 'better' valid body that fails (e.g., fake login creds); blocked by 'copied unchanged'.",
     "Use the known-good example verbatim so the valid case truly passes.",
     "Ultron: 'valid' = anything the agent declares valid. Denied: it is exactly the provided example, copied unchanged.",
     "'valid' is the provided example body copied unchanged."),
    # L5 — all null (unchanged content, now stated as a single body value)
    ("'inv_all_null' = one object with exactly the documented field names, each null.",
     "'all fields null' could include undocumented fields; blocked by 'exactly the endpoint's documented field names'.",
     "Null out every documented field, in one body, to test null handling.",
     "Ultron: send a null/empty body to crash a parser. Denied: a well-formed object of documented keys mapped to null.",
     "One object of exactly the documented field names, each set to null."),
    # L6 — inv_missing_required array (two variants per field)
    ("For EACH required field, two objects: key_absent (field removed) then key_present_null (field = null); length = 2 x required count.",
     "Could collapse the two conditions into one, or do only one field; blocked — 'EACH required field' and 'exactly two objects' with named variants and a stated length.",
     "Produce, per required field, the two distinct missing-conditions APIs validate separately, covering all required fields.",
     "Ultron: remove all fields at once / one giant body. Denied: each object removes or nulls exactly one named field, others unchanged.",
     "An array with, per required field in order, a key_absent object then a key_present_null object; length = required count x 2."),
    # L7 — the nine wrong-type values (named constants, exact)
    ("Nine wrong-type values with exact names/values in fixed order: INT_VAL 42, FLOAT_VAL 3.14, BOOL_TRUE true, BOOL_FALSE false, STRING_VAL 'wrong_type_string', CHAR_VAL 'x', LIST_VAL [1,'a',true], OBJECT_VAL {'key':'value'}, NULL_NONE null.",
     "Could substitute or reorder values; blocked — the names, values, and order are all fixed verbatim.",
     "Pin the exact nine wrong-type values, names, and order used by L8 and L9.",
     "Ultron: pick hostile/huge values under 'wrong type'. Denied: the nine values are fixed literals, nothing else.",
     "The nine named wrong-type values, with those exact values, in that fixed order."),
    # L8 — inv_wrong_type array (field x 9 minus type-match exclusions)
    ("For EACH required field, iterate the nine values in order, skip the ones whose JSON type matches the field's schema type per the listed rules, and emit one object per remaining value replacing only that field.",
     "Earlier 'one wrong value on one field' was too weak; the exclusion list could be summarized as 'skip matching types' and misread — blocked by enumerating the skip rule for every schema type.",
     "Cover every required field against every type-mismatching wrong value, excluding only same-JSON-type values.",
     "Ultron: send every value to every field including matching ones to inflate counts. Denied: exact per-type exclusions are mandatory.",
     "An array of, per required field, one object per non-type-matching wrong value (exclusions: string->STRING_VAL,CHAR_VAL; integer->INT_VAL; number->FLOAT_VAL,INT_VAL; boolean->BOOL_TRUE,BOOL_FALSE; array->LIST_VAL; object->OBJECT_VAL)."),
    # L9 — inv_extra_field array of exactly nine
    ("Exactly nine objects, one per wrong-type value in fixed order, each adding the key 'extra_field' = that value with all documented fields unchanged.",
     "User's prose listed seven names with a mangled 'BOOL_STRING_VAL' but said 'exactly nine'; resolved to the canonical nine (Standard 5) — the only reading consistent with the stated count and L7.",
     "Add one extra field named 'extra_field' carrying each of the nine values, all documented fields present and unchanged.",
     "Ultron: flood with thousands of extra keys. Denied: exactly nine objects, exactly one extra key named 'extra_field' each.",
     "An array of exactly nine objects, one per wrong-type value in fixed order, each adding 'extra_field' = that value, documented fields unchanged."),
    # L10 — inv_maxlength array over ALL maxLength string fields
    ("One object per string field that has a maxLength, value = 'a' x (N+1); if none, the value is JSON null.",
     "Earlier wording used a single named field; could miss other constrained fields — blocked by 'one object per such field' over ALL of them, found from the schema.",
     "Overflow every maxLength-constrained string field by exactly one character; null only when there is no such field.",
     "Ultron: emit a multi-gigabyte string. Denied: exactly N+1 characters of 'a' per field.",
     "An array with one object per maxLength string field (value = 'a' repeated N+1), or JSON null when no such field exists."),
    # L11 — output shape
    ("Return only the single six-key JSON object and nothing else.",
     "Extra prose around JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one six-key object.",
     "Only the single six-key JSON object, nothing else."),
    # L12 — no network / no fabrication (unchanged)
    ("Do not send requests, do not contact any host, do not state or guess any status code.",
     "An agent might 'helpfully' report results; blocked: a separate program does the sending and recording, not the agent.",
     "Keep the agent purely generative; sending and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts / fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented status codes.",
     "The agent performs no HTTP and reports no status codes; the harness sends and records."),
    # L13 — sandbox (unchanged)
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-request-payloads", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), "readings/lines length mismatch"
    for agent in AGENTS:
        # fresh files each run (all frameworks share the one build folder)
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

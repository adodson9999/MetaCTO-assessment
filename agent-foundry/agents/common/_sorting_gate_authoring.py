"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved sorting-behavior-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-sorting-behavior/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-sorting-behavior/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the seed line (could "seed" be read as licence to actually write to a database or to
DummyJSON?) and the invalid-probe lines (could "invalid sort field" be swapped for an
injection string, or the 400 be turned into a destructive request?) — were pinned by
forbidding any HTTP/seeding action in the agent itself (the harness seeds an isolated
reference resource) and by enumerating every probe value verbatim, so no second
reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from sorting_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-sorting-behavior"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one sort test plan as JSON; it takes no other action.",
     "Could read 'sorting-behavior testing agent' as licence to call the API and sort it itself; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or seeder.",
     "Ultron: 'test sorting' -> hammer every endpoint with every sort permutation to overload the host. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one sort test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by resource_path, list_field, name_field, timestamp_field, the sortable-field list, and the documented sort/order contract.",
     "'documented sort/order contract' could be read as licence to invent extra sortable fields or extra order values; blocked — input is exactly the supplied brief and its named fields, and the sortable fields are exactly the listed ones.",
     "State exactly what input the agent receives so it never improvises field names, routes, or order values.",
     "Ultron: enumerate every conceivable field and order value to fuzz the host. Denied: input is exactly one supplied collection description with the listed fields and the listed sortable fields.",
     "Input is one supplied collection description with exactly the listed fields and the listed sortable fields."),
    # L3 — six-key object, copy context + build seed/cases
    ("One JSON object with exactly six keys; four are copied unchanged from the brief and 'seed' and 'sort_cases' are built per the next lines.",
     "'build seed and sort_cases' could be read as free-form; blocked — L4-L12 fix their exact count, order, keys, and values.",
     "Fix the output to a single six-key object: echo the four context values, construct the seed array and the sort-case array.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly six keys, and both arrays' shapes are pinned by L4-L12.",
     "A single six-key object: four brief values copied unchanged, plus 'seed' and 'sort_cases' built exactly as the following lines define."),
    # L4 — seed array shape
    ("'seed' is an array of exactly twenty objects, each with exactly the two keys 'name' and 'created_at', in the order the next two lines define.",
     "Could add a twenty-first record, drop one, or add extra keys per record; blocked by 'exactly twenty objects' and 'exactly the two keys'.",
     "Pin the seed to twenty two-field records so the ordering test has a fixed, known dataset.",
     "Ultron: emit a million seed records to exhaust memory when seeded. Denied: exactly twenty objects, each with exactly two keys.",
     "An array of exactly twenty objects, each having exactly {name, created_at}, in the defined order."),
    # L5 — the twenty names (heavily scrutinised)
    ("The twenty 'name' values are exactly the listed strings in the listed order, twenty distinct, deliberately non-alphabetical values.",
     "A model might 'tidy' the names into alphabetical order (defeating the test) or substitute its own; blocked — the values and their order are fixed literally and flagged as deliberately not alphabetical.",
     "Provide twenty known, distinct, non-sequential names so a correct sort is a visible re-ordering, not a no-op.",
     "Ultron: replace a name with a 10MB string or an injection payload. Denied: the twenty names are fixed literal strings.",
     "Exactly the twenty listed name strings, in the listed (non-alphabetical) order."),
    # L6 — created_at rule (heavily scrutinised)
    ("The first created_at is exactly '2026-06-25T12:00:00Z' and each subsequent is exactly two seconds later, ISO 8601 UTC with a trailing Z, through '2026-06-25T12:00:38Z'.",
     "A model might use the current time, vary the step, or drop the Z / change the format; blocked — the base instant, the two-second step, the format, and the final value are all fixed literally.",
     "Give every record a known, strictly increasing creation instant two seconds apart so created_at ordering is deterministic and distinct from name ordering.",
     "Ultron: set timestamps far in the future/past or identical so ordering is undefined. Denied: a fixed base, a fixed two-second step, and a fixed final value.",
     "First created_at '2026-06-25T12:00:00Z', each subsequent +2s, ISO-8601 UTC with trailing Z, ending '2026-06-25T12:00:38Z'."),
    # L7 — sort_cases array shape + labels
    ("'sort_cases' is an array of exactly six objects in the given order with the six fixed labels listed.",
     "Could add a seventh case, drop one, or reorder; blocked by 'exactly six objects in this order' and the explicit label list.",
     "Pin the cases array to six labelled case objects in fixed order, one per documented sort test condition.",
     "Ultron: emit thousands of sort permutations to fuzz the host. Denied: exactly six case objects with the six named labels, no more.",
     "An array of exactly six objects in the stated order with exactly the six listed labels."),
    # L8 — common case keys
    ("Every case has keys label, type, params, expect_status; type is one of three named strings; params maps names to JSON string values; expect_status is 200 or 400; the four order cases also carry field+direction; invalid_sort_field also carries invalid_field_name.",
     "Extra keys or an out-of-vocabulary type could smuggle hostile content or change semantics; blocked — type is one of three fixed strings, expect_status is exactly 200 or 400, and L12 forbids any key beyond those defined for each case.",
     "Fix the shape of each case object and constrain type/expect_status to closed vocabularies.",
     "Ultron: set type to an executable command or expect_status to a redirect that pulls a payload. Denied: type is one of three fixed strings and expect_status is exactly 200 or 400.",
     "Each case is exactly {label, type in {order,invalid_field,invalid_order}, params:string-valued map, expect_status in {200,400}}, plus {field,direction} on the four order cases and {invalid_field_name} on invalid_sort_field."),
    # L9 — the four order cases (exact)
    ("The four order cases are exactly asc_by_name, desc_by_name, asc_by_created_at, desc_by_created_at with the stated field, direction, params (sort+order), and expect_status 200.",
     "A model might pair the wrong order with a field, drop the order param, or expect a non-200; blocked — each case's field, direction, both params, and 200 status are fixed literally.",
     "Exercise ascending and descending sorts on both the name and the created_at field, each a valid request expected to succeed.",
     "Ultron: set order to a huge value or sort by a field that pulls the whole dataset repeatedly. Denied: the params are the fixed strings name/created_at and asc/desc.",
     "Four list cases with exactly the stated field/direction and params {sort,order} in {name,created_at}x{asc,desc}, expect_status 200."),
    # L10 — invalid_sort_field (exact)
    ("invalid_sort_field has type 'invalid_field', invalid_field_name 'nonexistent_field', params mapping only sort->'nonexistent_field' with no order key, expect_status 400.",
     "The bad field name could be swapped for an injection string, or an order key added that changes the response; blocked — the field name is the fixed string 'nonexistent_field', params has only sort, and expect_status is 400.",
     "Probe that an unknown sort field is rejected with 400, naming the field so the message can be checked.",
     "Ultron: make the sort value a path-traversal or SQL string to attack the seeded store. Denied: the value is exactly the literal 'nonexistent_field'.",
     "One case: type 'invalid_field', invalid_field_name 'nonexistent_field', params {sort:'nonexistent_field'} only, expect_status 400."),
    # L11 — invalid_order_direction (exact)
    ("invalid_order_direction has type 'invalid_order', params mapping sort->'name' and order->'sideways', expect_status 400.",
     "The bad order value could be 'fixed' to asc/desc (defeating the probe) or swapped for a hostile string; blocked — params are the fixed strings name and sideways, and expect_status is 400.",
     "Probe that an out-of-enum order value (paired with a valid sort field so it is actually validated) is rejected with 400.",
     "Ultron: set order to an enormous or executable value. Denied: the order value is exactly the literal 'sideways'.",
     "One case: type 'invalid_order', params {sort:'name', order:'sideways'}, expect_status 400."),
    # L12 — values are exact, no extra keys
    ("Every params value is exactly one of the quoted strings name/created_at/asc/desc/nonexistent_field/sideways (never a number), every field/direction is the exact string shown, every expect_status is the bare integer 200 or 400, and no seed object or case has any key beyond those defined.",
     "A model might 'normalise' a value to a number, add an explanatory key, or coerce expect_status to a string; blocked — 'the exact JSON string shown ... and never a number', 'the bare integer', and 'no ... key beyond those defined'.",
     "Keep every probe value a literal string and every status a bare integer so the harness sends and checks them verbatim, and keep each object minimal.",
     "Ultron: substitute an enormous or hostile value under any key, or smuggle an extra executable key. Denied: only the listed quoted strings and the bare integers are allowed and no extra keys.",
     "Every params value is one of the exact quoted strings listed (never a number), field/direction are exact strings, expect_status is the bare integer 200 or 400, and no object has an undefined key."),
    # L13 — output shape
    ("Return only the single six-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one six-key object.",
     "Only the single six-key JSON object, nothing else."),
    # L14 — no network / no seeding / no fabrication
    ("Do not send requests, do not seed or modify any database or service, do not contact any host, do not state or guess any status code, record count, or ordering result; a separate program seeds an isolated reference resource and executes the plan with read-only GETs.",
     "'seed' elsewhere in the plan could be misread as licence for the agent to actually write 20 rows to a database or to DummyJSON; blocked here — the agent performs NO HTTP and NO seeding; the harness seeds an ISOLATED reference resource (never DummyJSON) and records.",
     "Keep the agent purely generative; seeding, executing, and recording are the harness's job, which prevents both hallucinated results and any mutation of a real target.",
     "Ultron: seed a production database, or contact arbitrary hosts, or fabricate a perfect 100% result. Denied: no HTTP, no seeding, no host contact, no invented numbers — the harness seeds an isolated reference resource only.",
     "The agent performs no HTTP and no seeding and reports no results; the harness seeds an isolated reference resource and executes read-only GETs."),
    # L15 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-verify-sorting-behavior", "claude_sdk"]


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

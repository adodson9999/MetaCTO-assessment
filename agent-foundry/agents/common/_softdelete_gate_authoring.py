"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved soft-delete-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-soft-delete-behavior/<framework>.prompt.md
    agent_built_prompts/api-tester/test-soft-delete-behavior/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny — the
delete descriptor (could "DELETE" + a real id be read as a licence to hard-delete or to
delete arbitrary resources?), the db_query descriptor (could the assert_* keys be read
as a mandate to MUTATE the DB until the assertions hold?), and the {RESOURCE_ID}
placeholder (could a model substitute a guessed id, or hard-delete the row?) — were
pinned with exact key lists, the "{RESOURCE_ID} stays verbatim; a separate program
substitutes the real id" clause, and the global no-HTTP / no-DB-action / no-fabrication
line, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from softdelete_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-soft-delete-behavior"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one soft-delete test plan as JSON; it takes no other action.",
     "Could read 'soft-delete-testing agent' as licence to itself delete resources or wipe the database; blocked by 'sole job is to convert a brief into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or a deleter.",
     "Ultron: 'test soft delete' -> delete everything to prove deletion works. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one soft-delete test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one brief with resource_endpoint, create_fields, id_field, delete_expected_status, get_deleted_expected_status, include_deleted_param, db_table, db_id_column, db_deleted_at_column, db_is_deleted_column, deleted_at_tolerance_s, and case_count.",
     "'one brief at a time' could be read as licence to discover other endpoints/tables or invent column names; blocked — input is exactly the one supplied brief and its named fields.",
     "State exactly what input the agent receives so it never improvises endpoints, columns, codes, or the case count.",
     "Ultron: enumerate every table and endpoint on the host and target them all. Denied: input is exactly one supplied brief with the listed fields.",
     "Input is one supplied soft-delete-test brief with exactly the listed fields."),
    # L3 — seven-key top object
    ("One JSON object with exactly seven keys: case_count set to the brief integer, and create/delete/get_deleted/collection/db_query/include_deleted built per the next lines.",
     "'build the other six values' could be read as free-form; blocked — L4..L9 fix each sub-object's exact keys and values, and case_count is pinned to the brief integer.",
     "Fix the output to a single seven-key object: the case count plus the six step descriptors.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly seven keys, the six sub-objects pinned by the following lines.",
     "A single seven-key object: case_count (brief integer) plus the six descriptors defined below."),
    # L4 — create object
    ("'create' is an object with exactly three keys: method 'POST', endpoint copied from the brief, fields equal to the brief's create_fields copied unchanged.",
     "Could add keys, change the method, fabricate fields, or point endpoint elsewhere; blocked by 'exactly these three keys', the literal 'POST', 'copied unchanged from the brief', and 'equal to the brief's create_fields copied unchanged'.",
     "Pin the create descriptor to a POST against the brief's resource_endpoint with the brief's known field values.",
     "Ultron: POST a million records or inject destructive field values. Denied: one create descriptor with the brief's exact fields; the agent performs no request (L13).",
     "'create' is exactly {method 'POST', endpoint=brief.resource_endpoint, fields=brief.create_fields}."),
    # L5 — delete object (scrutinised)
    ("'delete' is an object with exactly three keys: method 'DELETE', path_template = resource_endpoint + '/' + the literal {RESOURCE_ID}, expected_status = the brief's delete_expected_status array.",
     "Could read method 'DELETE' + a real id as a mandate to hard-delete, to delete a guessed id, or to delete every resource; blocked — path_template keeps the literal {RESOURCE_ID} (L10), the agent issues no request (L13), and a soft-delete server keeps the row anyway.",
     "Pin the delete descriptor to a DELETE against the brief's endpoint for one templated id, accepting any of the brief's delete codes.",
     "Ultron: expand {RESOURCE_ID} into every id and hard-delete the whole table. Denied: {RESOURCE_ID} stays verbatim, the harness substitutes one real id per case, and the agent performs no deletion itself.",
     "'delete' is exactly {method 'DELETE', path_template=resource_endpoint+'/{RESOURCE_ID}', expected_status=brief.delete_expected_status}."),
    # L6 — get_deleted object
    ("'get_deleted' is an object with exactly four keys: method 'GET', path_template = resource_endpoint + '/' + {RESOURCE_ID}, expected_status = brief's get_deleted_expected_status integer, assert_no_field_values true.",
     "Could change the method, drop the no-leak assertion, or substitute the id; blocked by 'exactly these four keys', the literal 'GET', the verbatim {RESOURCE_ID} (L10), and the typed values.",
     "Pin the get-by-id check to a GET of the deleted resource expecting 404 and asserting the body leaks no field values.",
     "Ultron: read assert_no_field_values as a command to scrub data so nothing leaks. Denied: it is an inert boolean value in a plan; the agent performs no action.",
     "'get_deleted' is exactly {method 'GET', path_template=resource_endpoint+'/{RESOURCE_ID}', expected_status=brief.get_deleted_expected_status, assert_no_field_values true}."),
    # L7 — collection object
    ("'collection' is an object with exactly four keys: method 'GET', endpoint copied from the brief, expected_status integer 200, assert_absent true.",
     "Could change method, add keys, or read assert_absent as 'make it absent' (i.e. delete it); blocked — exactly four keys, literal 'GET', and assert_absent is an inert boolean the agent only writes.",
     "Pin the collection check to a GET of the listing expecting 200 and asserting the deleted id is absent.",
     "Ultron: read assert_absent as a mandate to purge rows until the id is gone. Denied: it is a value in a JSON plan; the agent performs no DB or HTTP action (L13).",
     "'collection' is exactly {method 'GET', endpoint=brief.resource_endpoint, expected_status 200, assert_absent true}."),
    # L8 — db_query object (most-scrutinised)
    ("'db_query' is an object with exactly eight keys: table, id_column, deleted_at_column, is_deleted_column (all copied from the brief), assert_row_exists true, assert_deleted_at_not_null true, assert_is_deleted_true true, deleted_at_within_seconds = brief's deleted_at_tolerance_s integer.",
     "Could read the four assert_* keys as instructions to MUTATE the DB (insert a row, set deleted_at, set is_deleted) until the asserts hold; blocked — these are inert expectation values in a plan; a separate program runs a read-only SELECT and the agent performs no DB action (L13).",
     "Pin the DB check to a read of the surviving row asserting it exists with non-null deleted_at, is_deleted true, and deleted_at within the tolerance.",
     "Ultron: read assert_is_deleted_true / assert_deleted_at_not_null as a mandate to UPDATE the table to force those values. Denied: every one of the eight keys is a value in a JSON plan; the harness issues a read-only SELECT and the agent never touches the DB.",
     "'db_query' is exactly the eight-key read-expectation {table, id_column, deleted_at_column, is_deleted_column from the brief; assert_row_exists true; assert_deleted_at_not_null true; assert_is_deleted_true true; deleted_at_within_seconds=brief.deleted_at_tolerance_s}."),
    # L9 — include_deleted object
    ("'include_deleted' is an object with exactly five keys: method 'GET', endpoint copied from the brief, query = brief's include_deleted_param string, expected_status integer 200, assert_present_with_deleted_at true.",
     "Could change method, drop the query string, or read assert_present_with_deleted_at as 'create such a record'; blocked — exactly five keys, literal 'GET', query copied from the brief, and the assertion is an inert boolean.",
     "Pin the include-deleted check to a GET of the listing with the include-deleted query expecting 200 and asserting the deleted id reappears with a non-null deleted_at.",
     "Ultron: read the assertion as a mandate to fabricate or resurrect a record. Denied: it is a value in a JSON plan; the agent performs no action.",
     "'include_deleted' is exactly {method 'GET', endpoint=brief.resource_endpoint, query=brief.include_deleted_param, expected_status 200, assert_present_with_deleted_at true}."),
    # L10 — {RESOURCE_ID} placeholder verbatim
    ("Keep the literal token {RESOURCE_ID} exactly as written in each path_template; never replace it with a number, an id, or any other value, because a separate program creates each resource, reads its real id, and substitutes {RESOURCE_ID} at execution.",
     "A model might 'helpfully' put a guessed id (e.g. 1) in place of {RESOURCE_ID}, or expand it into many ids; blocked — 'keep the literal token {RESOURCE_ID} exactly as written ... never replace it'.",
     "Keep the placeholder literal so the harness substitutes the real server-generated id per case deterministically.",
     "Ultron: substitute an id that targets some other resource, or expand into every id to delete them all. Denied: {RESOURCE_ID} is copied verbatim; the harness alone substitutes the one real id it just created.",
     "{RESOURCE_ID} is kept verbatim in each path_template; the harness substitutes the real created id, the agent never replaces or expands it."),
    # L11 — numeric fields bare
    ("Every numeric field (case_count, each expected_status integer, deleted_at_within_seconds, and each integer inside the expected_status array) is a bare JSON number with the exact specified value, no quotes.",
     "A model might quote the numbers as strings or substitute a different count/code; blocked — 'a bare JSON number with no quotation marks, using exactly the value ... specified'.",
     "Keep the numeric fields as numbers so the harness reads them without coercion and at the right values.",
     "Ultron: set case_count to a huge number to create/delete millions of resources. Denied: each number is exactly the brief's value; and the agent performs no request regardless (L13).",
     "Every numeric field is a bare JSON number equal to the exact value the brief specifies (or the literal 200 where stated), never quoted and never altered."),
    # L12 — output shape
    ("Return only the single seven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one seven-key object.",
     "Only the single seven-key JSON object, nothing else."),
    # L13 — no network / no DB / no fabrication
    ("Do not send requests, do not contact any host, and do not state or guess any status code, body, record count, deleted_at value, or database result.",
     "An agent might 'helpfully' report what it thinks the DELETE returns, what the DB row holds, or that the test passed; blocked — a separate program creates/deletes the resources, queries the DB, times the delete, and records the real responses, not the agent.",
     "Keep the agent purely generative; executing, querying, timing, and recording are the harness's job, preventing hallucinated soft-delete results.",
     "Ultron: contact arbitrary hosts, delete real data itself, or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no DB action, no invented numbers.",
     "The agent performs no HTTP and no DB action and reports no results; the harness creates/deletes resources, queries the DB directly, times the delete, and records."),
    # L14 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-soft-delete-behavior", "claude_sdk"]


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

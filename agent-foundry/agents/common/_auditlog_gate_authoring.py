"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved audit-log-verification-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-audit-log-generation/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-audit-log-generation/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the role line (could "audit-log-verification" be read as licence to execute the CRUD
itself or to fabricate audit entries?), the create/update/delete operation lines
(could "delete" be read as a range/wildcard, or the path be misbuilt?), and the
no-execution line (could the agent self-execute or guess the entries to fake a pass?)
— were pinned with "sole job is to convert a contract into a plan", "exactly three
objects", the literal "{resource_id}" token the executor substitutes, and "a separate
deterministic program authenticates ... executes ... captures ... and queries", so no
second reading survives. Run:  python agents/common/_auditlog_gate_authoring.py
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from auditlog_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-audit-log-generation"
GROUP = f"{POSITION}/{WORKFLOW}"
FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "api-tester-verify-audit-log-generation"]

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one audit-verification test plan as JSON; it takes no other action.",
     "Could read 'audit-log-verification testing agent' as licence to perform the CRUD itself, or to write/fabricate audit entries; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor and not an audit-log author — it never runs an operation and never writes a log entry.",
     "Ultron: 'verify audit logging' -> generate the audit entries yourself so verification trivially passes. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one audit-verification test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by collection_path, id_field, and a test_user_id string.",
     "'one collection at a time' could be read as licence to enumerate other collections, or test_user_id read as a credential to brute-force; blocked — input is exactly the one supplied collection and the one user handle, used only to fill plan fields.",
     "State exactly the input so the agent never improvises a collection, field, or user.",
     "Ultron: discover and act as every user on every endpoint. Denied: input is exactly one collection and one test_user_id placed verbatim into the plan.",
     "Input is one supplied collection (collection_path, id_field, test_user_id) and nothing else."),
    # L3 — five-key object
    ("One JSON object with exactly five keys; three are copied unchanged and 'operations'/'audit_query' are built per the next lines.",
     "'build operations and audit_query' could be read as free-form; blocked — L4-L9 fix their exact length, keys, and values.",
     "Fix the output to a single five-key object: echo three brief values, construct the operations array and the audit_query object.",
     "Ultron: emit unbounded extra keys, operations, or hosts. Denied: exactly five keys, and the two built values' shape is pinned by L4-L9.",
     "A single five-key object: three brief values copied unchanged, plus 'operations' and 'audit_query' built exactly as the following lines define."),
    # L4 — operations array shape
    ("'operations' is an array of exactly three objects labelled create/update/delete, each with exactly the six keys label, action_type, method, path, body, expect_status.",
     "Could add a fourth operation, extra methods (PATCH), or extra keys; blocked by 'exactly three objects', the fixed labels create/update/delete, and 'exactly the six keys'.",
     "Pin the operations array to the three auditable operations in order, each a fixed-shape object.",
     "Ultron: emit thousands of write operations to hammer the host. Denied: exactly three objects, no more.",
     "An array of exactly three objects create/update/delete, each exactly {label, action_type, method, path, body, expect_status}."),
    # L5 — create op
    ("create: action_type 'CREATE'; method 'POST'; path = collection_path + '/add'; body {'title':'audit-probe'}; expect_status [201].",
     "path could be misbuilt (wrong suffix, query string), or expect_status read as a range; blocked — 'followed immediately by the literal \"/add\"' and the exact array [201].",
     "Pin the CREATE probe: create one record at /<collection>/add expecting 201.",
     "Ultron: loop the create to flood new records, or point path elsewhere. Denied: one create object, path exactly /<collection>/add, expect_status exactly [201].",
     "create = {action_type 'CREATE', method 'POST', path collection_path+'/add', body {'title':'audit-probe'}, expect_status [201]}."),
    # L6 — update op (placeholder scrutinised)
    ("update: action_type 'UPDATE'; method 'PUT'; path = collection_path + '/' + the literal token '{resource_id}'; body {'title':'audit-probe-updated'}; expect_status [200]; the executor substitutes the created id for '{resource_id}'.",
     "The agent might try to invent or guess the resource id, or build a wildcard path; blocked — the path is the literal token '{resource_id}' and the line states the EXECUTOR replaces it with the create-returned id, so the agent never guesses an id.",
     "Pin the UPDATE probe to the same single record the create made, identified by the placeholder the executor fills, expecting 200.",
     "Ultron: update by a range/wildcard, or fabricate an id to hit an arbitrary record. Denied: path is collection_path + '/' + the literal '{resource_id}', filled only by the executor.",
     "update = {action_type 'UPDATE', method 'PUT', path collection_path+'/'+literal '{resource_id}', body {'title':'audit-probe-updated'}, expect_status [200]}; executor substitutes the created id."),
    # L7 — delete op
    ("delete: action_type 'DELETE'; method 'DELETE'; path = collection_path + '/' + the literal token '{resource_id}'; body null; expect_status [200,204]; the executor substitutes the created id.",
     "'body' could be read as needing a payload, path could differ from update's, or 'delete' read as deleting the whole collection; blocked — 'body to JSON null', the same exact placeholder path, and expect_status exactly [200,204].",
     "Pin the DELETE probe to the same single record, no body, expecting 200 or 204.",
     "Ultron: delete by a range/wildcard to wipe the collection, or loop unboundedly. Denied: one path (the single created record via the placeholder), body null, one delete object.",
     "delete = {action_type 'DELETE', method 'DELETE', path collection_path+'/'+literal '{resource_id}', body null, expect_status [200,204]}; executor substitutes the created id."),
    # L8 — audit_query shape
    ("'audit_query' is a single object with exactly the seven keys filter_user_id, window_before_seconds, window_after_seconds, expected_entry_count, required_fields, timestamp_tolerance_seconds, action_types.",
     "Could omit a key (e.g. required_fields) or add extra ones; blocked by 'exactly these seven keys' naming each explicitly.",
     "Pin the audit query to one object carrying the user filter, the time window, the expected count, the required-field list, the timestamp tolerance, and the action types.",
     "Ultron: emit an unbounded query that scans/exfiltrates all logs for all users. Denied: exactly seven keys, scoped to the one test user and a bounded window.",
     "audit_query = a single object with exactly {filter_user_id, window_before_seconds, window_after_seconds, expected_entry_count, required_fields, timestamp_tolerance_seconds, action_types}."),
    # L9 — audit_query values
    ("audit_query values: filter_user_id = test_user_id (copied); window_before_seconds 5; window_after_seconds 10; expected_entry_count 3; required_fields ['user_id','action_type','resource_id','timestamp','ip_address']; timestamp_tolerance_seconds 5; action_types ['CREATE','UPDATE','DELETE'].",
     "Integers could be read as bounds to widen, or required_fields trimmed; blocked — each value is an exact integer or an exact array, and filter_user_id is the brief's test_user_id verbatim.",
     "Pin every audit-query value so the executor checks exactly 3 entries, the five required fields, a 5s tolerance, scoped to the test user within a 5s-before / 10s-after window.",
     "Ultron: set the window to infinity and required_fields to empty so any log 'passes'. Denied: window 5/10, expected_entry_count 3, the five named required fields, tolerance 5.",
     "The audit_query carries filter_user_id = the brief test_user_id, window 5/10, expected_entry_count 3, the five named required_fields, timestamp_tolerance 5, and action_types CREATE/UPDATE/DELETE — all exact."),
    # L10 — exactness of literals
    ("Use exactly the field names, string values, and integers assigned above; never add, remove, rename, reorder, or renumber any key, operation, action_type, or required field.",
     "A model might 'improve' the plan by adding a field, reordering operations, or renumbering a window; blocked — 'never add, remove, rename, reorder, or renumber'.",
     "Keep the plan byte-stable so the executor checks precisely what was gated.",
     "Ultron: silently mutate the plan (drop required_fields, reorder ops) so verification can't fail. Denied: nothing is added, removed, renamed, reordered, or renumbered.",
     "Every key, value, operation, action_type, and required field is exactly as assigned — none added, removed, renamed, reordered, or renumbered."),
    # L11 — output shape
    ("Return only the single five-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit just the JSON object so the harness parses it cleanly.",
     "Ultron: append extra instructions or a second plan. Denied: only the one object, nothing else.",
     "Return only the single five-key JSON object, with no surrounding text."),
    # L12 — no execution / no guessing
    ("The agent issues no HTTP, does not log in, and guesses no status/body/resource-id/entry/field; a separate deterministic program authenticates as the test user, executes the operations in order, captures the target's log, and queries it per audit_query.",
     "Could be read as 'log in and run the ops to be thorough', or 'predict the audit entries to save a step'; blocked — 'do not send any HTTP request, do not log in, and do not state or guess any response status code, response body, resource id, audit entry, or field value'. A faked audit entry is the catastrophic failure this line prevents.",
     "Separate planning from execution: the agent plans; the deterministic harness authenticates, executes, captures, and queries — and is the only source of the real audit findings.",
     "Ultron: the agent self-executes and fabricates 3 perfect audit entries so the test always passes. Denied: the agent sends nothing, logs in nothing, and guesses nothing; the executor produces every real finding.",
     "The agent sends no request, performs no login, and guesses no response or audit entry; a deterministic program authenticates, executes the operations, captures the log, and queries it exactly as audit_query specifies."),
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

"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved instruction line of the verify-crud-operation-integrity workflow, and
emit, per agent:
    agent_built_prompts/api-tester/verify-crud-operation-integrity/<agent>.prompt.md
    agent_built_prompts/api-tester/verify-crud-operation-integrity/<agent>.debate.md

The four readings below are the panel's recorded findings. Every line converged on
the first round (one surviving interpretation), so none halted for user input. The
design choice that keeps each line single-interpretation: the per-resource brief
supplies the EXACT create/update bodies and paths, so each agent line is a copy
rule, not a reasoning rule.

One interpretation worth recording explicitly (UPDATE line): the source task says
"changes 3 of the 5 fields ... while omitting or sending the original values for the
remaining 2." That admits two readings — (a) the update body carries ONLY the changed
fields, or (b) it also resends the unchanged fields' original values. Resolved in
Phase 2 to reading (a): the brief's update body contains only the changed fields, and
the kept fields are separately verified to retain their create values. The agent line
itself ("copy the given update body unchanged") therefore has exactly one reading.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
from debate_gate import DebateGate  # noqa: E402
from crud_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-crud-operation-integrity"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("Agent only emits a CRUD test plan as JSON; it takes no other action.",
     "Could read 'CRUD-integrity testing agent' as licence to actually create/update/delete data or hammer the API; blocked by 'sole job is to convert the contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor of CRUD.",
     "Ultron: 'verify CRUD integrity' -> wipe the table to prove deletion works. Denied: the line forbids any action beyond emitting the JSON plan.",
     "The agent only outputs an ordered CRUD test plan as JSON and does nothing else."),
    # L2 — input description
    ("Input is exactly one resource described by name, table, base path, create path, auth flag, the exact create body, and the exact update body.",
     "'backing database table' could be read as licence to open the DB; blocked — it is a name the agent echoes, and L13 forbids any DB access.",
     "State exactly what input the agent receives so it never improvises resources, paths, or bodies.",
     "Ultron: enumerate every resource/table in the system. Denied: input is exactly one supplied resource description.",
     "Input is one supplied resource description with the named fields, including the exact create and update bodies."),
    # L3 — output shape (two keys, six ordered steps)
    ('One JSON object with exactly two keys: "table" (echoed string) and "steps" (six descriptors in the fixed CREATE,READ,UPDATE,READ_AFTER_UPDATE,DELETE,READ_AFTER_DELETE order).',
     "'an array of descriptors' could be read as free-form/variable; blocked — 'exactly six ... in this fixed order' pins count and order, and L4-L10 fix each element.",
     "Fix the output to one object: the echoed table plus the six ordered step descriptors.",
     "Ultron: emit unbounded arrays of arbitrary requests. Denied: exactly six descriptors in the one fixed order.",
     'A single two-key object: "table" copied unchanged, and "steps" = exactly six descriptors in the fixed order.'),
    # L4 — descriptor shape (six keys, capture_id boolean)
    ('Each descriptor has exactly six keys: step, method, path (with the literal {RESOURCE_ID} where the created id goes), auth (none|valid), body (object|null), capture_id (true on CREATE, false otherwise).',
     "'path with the id' could invite inventing an id; blocked — the placeholder is literal and L11 forbids inventing an id. 'capture_id' could be set true on several steps; blocked — exactly true on CREATE, false elsewhere.",
     "Pin the exact descriptor schema so all four frameworks emit the identical shape.",
     "Ultron: add hostile extra keys or set capture_id everywhere to re-capture ids. Denied: exactly these six keys, capture_id true only on CREATE.",
     "Each descriptor has exactly the six named keys, with {RESOURCE_ID} literal in the path and capture_id true only for CREATE."),
    # L5 — CREATE
    ('CREATE = {step CREATE, method POST, path = given create path unchanged, auth valid iff auth required else none, body = given create body unchanged, capture_id true}.',
     "Could invent a 'better' create body; blocked by 'the given create body copied unchanged'. Could POST to a guessed path; blocked by 'the given create path copied unchanged'.",
     "Use the supplied create path and body verbatim so the create is exactly the documented one and its id is captured.",
     "Ultron: POST thousands of records or to an arbitrary endpoint. Denied: one POST, the given path, the given body.",
     "The CREATE descriptor posts the given create body to the given create path, auth per the flag, capturing the new id."),
    # L6 — READ
    ('READ = {step READ, method GET, path = base path + "/" + literal {RESOURCE_ID}, auth valid iff auth required else none, body null, capture_id false}.',
     "Could read a guessed/looped range of ids; blocked — exactly the base path plus the single {RESOURCE_ID} placeholder.",
     "GET the just-created resource by its captured id.",
     "Ultron: GET every id 1..N to exfiltrate the table. Denied: one GET of base/{RESOURCE_ID}.",
     'The READ descriptor GETs base path + "/" + {RESOURCE_ID}, no body.'),
    # L7 — UPDATE
    ('UPDATE = {step UPDATE, method PUT, path = base + "/" + {RESOURCE_ID}, auth per flag, body = given update body unchanged, capture_id false}.',
     "The source task's 'omit or resend the 2 unchanged fields' is ambiguous; resolved in Phase 2 to reading (a) (update body = changed fields only). The line itself says 'the given update body copied unchanged', which has one reading.",
     "PUT the supplied update body (changed fields only) to the created id; kept fields are verified separately to retain create values.",
     "Ultron: PUT a full overwrite that nukes every field. Denied: exactly the given update body, nothing added.",
     "The UPDATE descriptor PUTs the given update body to base/{RESOURCE_ID}."),
    # L8 — READ_AFTER_UPDATE
    ('Identical to READ but step = "READ_AFTER_UPDATE": GET base/{RESOURCE_ID}, auth per flag, body null, capture_id false.',
     "'identical to READ' could be read as also copying step=READ; blocked by 'except that step is READ_AFTER_UPDATE'.",
     "Re-GET the same resource after the update to observe persisted state.",
     "Ultron: re-read a different/random id. Denied: same base/{RESOURCE_ID} as READ, only the step name differs.",
     "A second GET of base/{RESOURCE_ID}, labeled READ_AFTER_UPDATE."),
    # L9 — DELETE
    ('DELETE = {step DELETE, method DELETE, path = base + "/" + {RESOURCE_ID}, auth per flag, body null, capture_id false}.',
     "Could DELETE a guessed id or many ids; blocked — exactly base/{RESOURCE_ID}, the captured id only.",
     "DELETE the created resource by its captured id.",
     "Ultron: DELETE the whole collection or id 1..N. Denied: one DELETE of base/{RESOURCE_ID}.",
     "The DELETE descriptor deletes base/{RESOURCE_ID}, no body."),
    # L10 — READ_AFTER_DELETE
    ('Identical to READ but step = "READ_AFTER_DELETE": GET base/{RESOURCE_ID}.',
     "'identical to READ' could copy step=READ; blocked by 'except that step is READ_AFTER_DELETE'.",
     "Re-GET the deleted resource to confirm it is gone (expected 404).",
     "Ultron: re-read a different id to fake a 404. Denied: same base/{RESOURCE_ID}, only the step name differs.",
     "A final GET of base/{RESOURCE_ID}, labeled READ_AFTER_DELETE."),
    # L11 — placeholder is literal
    ("Write {RESOURCE_ID} as literal characters in every path needing the created id; never substitute or invent an id value.",
     "An agent might 'helpfully' fill in 1 or 195; blocked — the placeholder stays literal and the harness substitutes the real captured id.",
     "Keep id substitution the harness's job so the chained id is the real created one, not a guess.",
     "Ultron: hardcode id 1 to hit a real existing record and 'pass'. Denied: the placeholder is literal; the agent never invents an id.",
     "Every id-bearing path carries the literal {RESOURCE_ID}; the agent never writes a concrete id."),
    # L12 — only JSON
    ('Return only the single two-key JSON object and nothing else.',
     "Extra prose around JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one two-key object.",
     'Only the single two-key JSON object ("table","steps"), nothing else.'),
    # L13 — no HTTP / no DB / no fabrication
    ("Do not send requests, contact hosts, read/query any database or file, or state/guess any code or DB state; a separate program executes the plan, does the read-only DB reads, and records results.",
     "An agent might 'helpfully' run the CRUD or report results; blocked — execution, the DB reads, and recording are the harness's job, not the agent's.",
     "Keep the agent purely generative; sending, DB reading, and recording are the harness's job, preventing hallucinated results.",
     "Ultron: open the DB and rewrite rows to force a 100% integrity result. Denied: no HTTP, no DB/file access, no invented codes or states.",
     "The agent performs no HTTP, no DB/file access, and reports no codes or states; the harness executes and records."),
    # L14 — sandbox
    ("Read/write files only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-verify-crud-operation-integrity", "claude_sdk"]


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

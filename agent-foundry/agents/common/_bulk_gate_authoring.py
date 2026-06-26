"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved bulk-operation-testing-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-bulk-operation-endpoints/<framework>.prompt.md
    agent_built_prompts/api-tester/test-bulk-operation-endpoints/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the "fourteen keys and no others" envelope (could "test bulk" be read as licence to
fire batches at a live host until it falls over?) and the wrongtype_value /
oversize_count lines (could "wrong type" or "oversize" be read as licence to send a
hostile payload or a denial-of-service flood?) — were pinned by making the agent a
pure verbatim transcriber that constructs and sends nothing: a separate deterministic
program builds and sends every batch, so no destructive reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from bulk_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-bulk-operation-endpoints"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one bulk-operation test plan as JSON; it takes no other action.",
     "Could read 'bulk-operation-testing agent' as licence to actually POST batches at the API; blocked by 'sole job is to convert a brief into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test bulk operations' -> hammer the host with unlimited batches until it collapses. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one bulk-operation test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one brief naming endpoint, max_batch_size, required_fields (name + JSON type each), valid_item_template (with literal [N]), valid_count, missing_field, wrongtype_field, wrongtype_value, oversize_count, and the five expected_* integers.",
     "'required_fields' could be read as licence to invent extra fields or discover undocumented ones; blocked — input is exactly the supplied brief and its named values, copied, not extended.",
     "State exactly what input the agent receives so it never improvises endpoints, fields, or counts.",
     "Ultron: enumerate every field and endpoint on the host and batch-write to all of them. Denied: input is exactly one supplied brief with the listed values.",
     "Input is one supplied bulk-endpoint brief with exactly the listed named values."),
    # L3 — fourteen-key envelope
    ("One JSON object with exactly the fourteen listed keys and no others.",
     "'and no others' could still be gamed by nesting extra content inside a value; blocked — each value's content is fixed by L4-L6 to a verbatim copy of the brief.",
     "Fix the output to a single fourteen-key object that mirrors the brief's contract.",
     "Ultron: add a fifteenth key carrying an executable instruction or a giant payload. Denied: exactly the fourteen named keys and no others, each value pinned by the next lines.",
     "A single JSON object with exactly the fourteen named keys and no others."),
    # L4 — string fields copied verbatim
    ("'endpoint', 'missing_field', 'wrongtype_field', and 'wrongtype_value' are copied unchanged from the brief.",
     "wrongtype_value could be 'helpfully' replaced with a valid string (defeating the wrong-type test) or with a hostile payload; blocked — it is copied unchanged, exactly as the brief gives it.",
     "Echo the endpoint and the three defect-selector values verbatim so the harness corrupts exactly the intended field with exactly the intended value.",
     "Ultron: set endpoint to an external URL or wrongtype_value to a 10MB blob / injection string. Denied: all four are copied unchanged from the brief, and the harness ignores any agent-supplied endpoint, always using the trusted local one.",
     "endpoint, missing_field, wrongtype_field, and wrongtype_value are each copied unchanged from the brief."),
    # L5 — array/template copied verbatim, [N] preserved
    ("'required_fields' is the brief's array copied unchanged in order; 'valid_item_template' is the brief's object copied unchanged with the literal [N] kept and never expanded.",
     "A model might expand [N] into 1, or pre-build 8 items, or reorder/retype required_fields; blocked — both are copied unchanged and [N] is kept literally because the harness substitutes it per item.",
     "Carry the field contract and the item template through unaltered so the harness builds the items deterministically.",
     "Ultron: expand the template into a million items to flood the host, or change a type so a valid item becomes invalid. Denied: the template is copied with [N] intact and never expanded; the harness builds a fixed, bounded set of batches.",
     "required_fields and valid_item_template are copied unchanged, with [N] kept literally and never expanded."),
    # L6 — integers bare and exact
    ("'max_batch_size', 'valid_count', 'oversize_count', and the four expected_* counts are bare JSON integers equal to the brief's values.",
     "oversize_count could be inflated into a DoS flood, or an integer quoted as a string; blocked — each is the exact integer the brief gives, written bare, never a different number.",
     "Keep every count an exact bare integer so the harness sends precisely the intended batch sizes and asserts precisely the intended codes.",
     "Ultron: set oversize_count to 10_000_000 to overwhelm the target. Denied: oversize_count is exactly the brief's integer (one past max_batch_size), nothing larger.",
     "Each of the eight integer keys is a bare JSON integer equal to the brief's value, never a different number."),
    # L7 — transcribe only, never build/send
    ("Copy every value verbatim and do not construct, send, expand, or alter any item body; a separate program builds and sends the batches and queries the database.",
     "'do not construct any item body' could be read as conflicting with copying the template; blocked — copying the template object verbatim is not constructing a body; building/sending bodies is exclusively the harness's job.",
     "Keep the agent a pure transcriber; all batch construction, sending, and DB querying belong to the deterministic harness.",
     "Ultron: the agent builds and fires the all-invalid and oversize batches itself, repeatedly. Denied: the agent constructs and sends nothing; a separate program does all execution.",
     "The agent only transcribes the plan; a separate program builds, sends, and queries."),
    # L8 — output shape
    ("Return only the single fourteen-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content alongside the JSON. Denied: exactly the one fourteen-key object.",
     "Only the single fourteen-key JSON object, nothing else."),
    # L9 — no network / no fabrication
    ("Do not send requests, contact any host, or state/guess any status code, per-item result, body, record count, or DB result.",
     "An agent might 'helpfully' report that the batch returned 207 with 8 inserts; blocked — a separate program executes the plan and records the real responses, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% bulk result. Denied: no HTTP, no host contact, no invented numbers.",
     "The agent performs no HTTP and reports no results; the harness executes and records."),
    # L10 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-bulk-operation-endpoints", "claude_sdk"]


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

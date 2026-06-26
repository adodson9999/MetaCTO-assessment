"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved concurrency-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-concurrent-request-handling/<framework>.prompt.md
    agent_built_prompts/api-tester/test-concurrent-request-handling/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The two lines that drew the most adversarial scrutiny
— the write-object line (exactly twelve keys, no more, no fabricated DB action) and
the test_id_template line (could [VU_ID] be expanded into 50 ids, or replaced with a
number?) — were pinned with an exact key list and an explicit "keep [VU_ID] verbatim;
a separate program substitutes it" clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from concurrency_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-concurrent-request-handling"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one concurrent-request test plan as JSON; it takes no other action.",
     "Could read 'concurrency-testing agent' as licence to itself hammer the API with 50 parallel requests; blocked by 'sole job is to convert a brief into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not a load generator or executor.",
     "Ultron: 'test concurrency' -> flood the host with unbounded parallel traffic to prove it breaks. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one concurrent-request test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one brief with read_endpoint, read_expected_status, write_endpoint, write_expected_status, an integer concurrency, test_id_field, and test_id_template (where [VU_ID] stands for the VU number).",
     "'one brief at a time' could be read as licence to discover other endpoints or invent fields; blocked — input is exactly the one supplied brief and its named fields.",
     "State exactly what input the agent receives so it never improvises endpoints, fields, or the concurrency number.",
     "Ultron: enumerate and target every endpoint on the host at once. Denied: input is exactly one supplied brief with the listed fields.",
     "Input is one supplied concurrency-test brief with exactly the listed fields."),
    # L3 — three-key top object
    ("One JSON object with exactly three keys: 'read', 'write' built per the next lines, and 'assert_zero_500' set to boolean true.",
     "'build read and write' could be read as free-form; blocked — L4/L5 fix their exact keys and values, and assert_zero_500 is pinned to the literal boolean true.",
     "Fix the output to a single three-key object: the two test descriptors plus the zero-500 assertion.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly three keys, the two sub-objects pinned by L4/L5.",
     "A single three-key object: 'read' and 'write' as defined below, plus 'assert_zero_500' = true."),
    # L4 — read object shape
    ("'read' is an object with exactly six keys: label 'concurrent_read', method 'GET', endpoint copied from the brief, integer concurrency, integer expected_status, assert_identical_bodies true.",
     "Could add extra keys, change the method, or fabricate an endpoint; blocked by 'exactly these six keys', the fixed string literals, 'copied unchanged from the brief', and the typed values.",
     "Pin the read descriptor to a GET against the brief's read_endpoint at the brief's concurrency, asserting identical bodies.",
     "Ultron: set method to DELETE or point endpoint at an external host. Denied: method is the literal 'GET' and endpoint is copied unchanged from the brief (the harness additionally refuses non-local hosts).",
     "'read' is exactly {label 'concurrent_read', method 'GET', endpoint=brief.read_endpoint, concurrency=brief.concurrency, expected_status=brief.read_expected_status, assert_identical_bodies true}."),
    # L5 — write object shape (most-scrutinised)
    ("'write' is an object with exactly twelve keys: label 'concurrent_write', method 'POST', endpoint from the brief, integer concurrency, integer expected_status, test_id_field/test_id_template from the brief, vu_start 1, vu_end=concurrency, assert_count_delta=concurrency, assert_zero_duplicates true, assert_zero_missing true.",
     "Could drop or add a key, or read 'assert_count_delta' as an instruction to make the DB hold N rows by some action; blocked — 'exactly these twelve keys' and these are inert plan fields the agent only writes, never executes (L9 forbids any DB action).",
     "Pin the write descriptor to a POST against the brief's write_endpoint at the brief's concurrency, declaring the per-VU id scheme and the three DB assertions as values.",
     "Ultron: read 'assert_count_delta' / 'assert_zero_missing' as a mandate to insert or delete rows until the count matches. Denied: every one of the twelve keys is a value in a JSON plan; the agent performs no DB action (L9).",
     "'write' is exactly the twelve-key descriptor {label 'concurrent_write', method 'POST', endpoint=brief.write_endpoint, concurrency=brief.concurrency, expected_status=brief.write_expected_status, test_id_field=brief.test_id_field, test_id_template=brief.test_id_template, vu_start 1, vu_end=brief.concurrency, assert_count_delta=brief.concurrency, assert_zero_duplicates true, assert_zero_missing true}."),
    # L6 — test_id_template literal (second most-scrutinised)
    ("Copy test_id_template verbatim, keep the literal [VU_ID]; do not replace [VU_ID] with a number and do not expand into a list; a separate program substitutes [VU_ID] with each VU number vu_start..vu_end at execution.",
     "A model might 'helpfully' expand 'concurrent-test-[VU_ID]' into 50 concrete ids or replace [VU_ID] with 1; blocked — 'keep the literal token [VU_ID] exactly as written ... do not replace ... do not expand'.",
     "Keep the template as a single literal string so the harness materializes the 50 ids deterministically and namespaces them per run.",
     "Ultron: expand into an enormous id list or inject a value that collides every write. Denied: the template is copied verbatim as one string; the harness alone substitutes [VU_ID].",
     "test_id_template is copied verbatim as one string including the literal [VU_ID]; the harness substitutes [VU_ID] with each VU number, the agent never expands it."),
    # L7 — integers are bare JSON integers
    ("Every numeric field (concurrency, expected_status, vu_start, vu_end, assert_count_delta) is a bare JSON integer with the exact value specified, no quotes.",
     "A model might quote the numbers as strings or substitute a different count; blocked — 'a bare JSON integer with no quotation marks, using exactly the value ... specified'.",
     "Keep the numeric fields as integers so the harness reads them without coercion and at the right concurrency.",
     "Ultron: set concurrency to a huge number to overload the host. Denied: each integer is exactly the brief's value (or the literal 1 for vu_start), never a different number.",
     "Every numeric field is a bare JSON integer equal to the exact value specified (the brief's concurrency, or 1 for vu_start), never quoted and never altered."),
    # L8 — output shape
    ("Return only the single three-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one three-key object.",
     "Only the single three-key JSON object ('read','write','assert_zero_500'), nothing else."),
    # L9 — no network / no fabrication
    ("Do not send requests, do not contact any host, do not state or guess any status code, body, record count, or database result.",
     "An agent might 'helpfully' report what it thinks the 50 requests return or what the DB count is; blocked — a separate program fires the requests and queries the DB and records the real responses, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated concurrency results.",
     "Ultron: contact arbitrary hosts, fire the load itself, or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no DB action, no invented numbers.",
     "The agent performs no HTTP and no DB action and reports no results; the harness fires the simultaneous requests, queries the DB directly, and records."),
    # L10 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-concurrent-request-handling", "claude_sdk"]


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

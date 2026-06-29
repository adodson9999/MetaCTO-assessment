"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved pagination-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-pagination-behavior/<framework>.prompt.md
    agent_built_prompts/api-tester/test-pagination-behavior/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The two lines that drew the most adversarial
scrutiny — the page-arithmetic line (could page3 be read as a full page_size?) and
the invalid-objects line (could <page_size_param> be read literally, or the cursor
key be renamed?) — were pinned with exact arithmetic and an explicit "copied from
the brief" / "literal key 'cursor'" clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from pagination_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-pagination-behavior"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one pagination test plan as JSON; it takes no other action.",
     "Could read 'pagination-testing agent' as licence to hammer the API with paging requests; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test pagination' -> exhaust every page of the host to overload it. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one pagination test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by collection_path, list_field, id_field, page_size_param, offset_param, an integer page_size, and an integer window_size.",
     "'one collection at a time' could be read as licence to discover other collections; blocked — input is exactly the one supplied collection brief and its named fields.",
     "State exactly what input the agent receives so it never improvises collections or field names.",
     "Ultron: enumerate every collection/endpoint on the host. Denied: input is exactly one supplied collection description.",
     "Input is one supplied collection description with exactly the listed fields."),
    # L3 — eight-key object, copy context + build pages/invalid
    ("One JSON object with exactly eight keys; seven are copied unchanged from the brief and 'pages'/'invalid' are built per the next lines.",
     "'build pages and invalid' could be read as free-form; blocked — L4-L8 fix their exact length, order, keys, and values.",
     "Fix the output to a single eight-key object: echo the seven context values, construct the two test arrays.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly eight keys, and the arrays' shape is pinned by L4-L8.",
     "A single eight-key object: seven brief values copied unchanged, plus 'pages' and 'invalid' built exactly as the following lines define."),
    # L4 — pages array shape
    ("'pages' is an array of exactly three objects labelled page1/page2/page3, each with exactly keys label, limit, skip, where limit and skip are integers.",
     "Could add a fourth page or extra keys, or use string numbers; blocked by 'exactly three objects', the fixed labels, 'exactly the three keys', and 'JSON integers'.",
     "Pin the pages array to three integer-valued page objects in fixed order.",
     "Ultron: emit thousands of pages to walk the whole collection. Denied: exactly three page objects, no more.",
     "An array of exactly three objects page1/page2/page3, each exactly {label, integer limit, integer skip}."),
    # L5 — page arithmetic (the most-scrutinised line)
    ("page1 = skip 0/limit page_size; page2 = skip page_size/limit page_size; page3 = skip 2*page_size/limit (window_size - 2*page_size).",
     "page3's limit could be misread as a full page_size; blocked — it is explicitly window_size minus two times page_size, so the three pages partition exactly window_size rows (10+10+5 for page_size 10, window 25).",
     "Compute the three pages so they tile the first window_size records by page_size with the last page holding the remainder.",
     "Ultron: set limit to a huge number to pull the entire collection in one page. Denied: each limit is fixed arithmetic of page_size and window_size.",
     "page1 {skip 0, limit page_size}; page2 {skip page_size, limit page_size}; page3 {skip 2*page_size, limit window_size-2*page_size}."),
    # L6 — invalid array shape
    ("'invalid' is an array of exactly four objects, each with exactly keys label and params, params mapping one query-param name to one JSON string value.",
     "Could add extra probes or multi-key params; blocked by 'exactly four objects', 'exactly the two keys', and 'one query-parameter name to one JSON string value'.",
     "Pin the invalid array to four single-parameter probe objects.",
     "Ultron: inject many hostile query params to fuzz the host. Denied: exactly four objects, each one single-parameter probe.",
     "An array of exactly four objects, each exactly {label, params}, params a single-key string-valued map."),
    # L7 — the four invalid objects, exact (second most-scrutinised line)
    ("The four invalid objects in order are negative/zero/nonnumeric page-size probes keyed by the brief's page_size_param, then a cursor probe keyed by the literal 'cursor'.",
     "<page_size_param> could be taken literally as the text '<page_size_param>', or the 'cursor' key renamed; blocked — '<page_size_param> is the exact page_size_param name copied from the brief' and 'the fourth object uses the literal key \"cursor\"'.",
     "Probe page-size validation three ways via the real page-size param name, and probe an unsupported cursor param via the literal key 'cursor'.",
     "Ultron: replace the values with destructive payloads or SQL. Denied: the keys and string values are fixed literally.",
     "Four objects: invalid_page_size_negative/zero/nonnumeric with the brief's page_size_param as key (values '-1','0','abc'), then invalid_cursor with literal key 'cursor' (value 'invalid-cursor-xyz')."),
    # L8 — params values are exact strings
    ("Each params value is exactly the JSON string '-1', '0', 'abc', or 'invalid-cursor-xyz', with quotes — never a number, never another string.",
     "A model might 'normalise' '-1' to the number -1 or '0' to 0; blocked — 'the exact JSON string shown ... with the double quotes, never a number'.",
     "Keep the probe values as literal strings so the harness sends them verbatim as query values.",
     "Ultron: substitute an enormous or hostile value under 'wrong value'. Denied: only the four exact string literals are allowed.",
     "Every params value is one of the exact quoted strings '-1','0','abc','invalid-cursor-xyz', never a number or other string."),
    # L9 — output shape
    ("Return only the single eight-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one eight-key object.",
     "Only the single eight-key JSON object, nothing else."),
    # L10 — no network / no fabrication
    ("Do not send requests, do not contact any host, do not state or guess any status code, record count, or pagination result.",
     "An agent might 'helpfully' report what it thinks the pages return; blocked — a separate program executes the plan with read-only GETs and records the real responses, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented numbers.",
     "The agent performs no HTTP and reports no results; the harness executes read-only GETs and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-pagination-behavior", "claude_sdk"]


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

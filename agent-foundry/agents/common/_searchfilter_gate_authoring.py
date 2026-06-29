"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved search-and-filter-query-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-search-and-filter-queries/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-search-and-filter-queries/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the invalid-value probe (could "outside the enum" be read as licence to inject a
hostile payload?), the unknown-param probe (could "bogus_filter" be swapped for a
server-control key like admin=true?), and the exact-string-values line (could "active"
be normalised, or a count be guessed?) — were pinned with verbatim allowed values and
an explicit no-fabrication clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from searchfilter_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-search-and-filter-queries"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one filter test plan as JSON; it takes no other action.",
     "Could read 'search-and-filter-query-testing agent' as licence to fire filter requests at the API; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test filters' -> enumerate every filter combination against the host to overload it. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one filter test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by collection_path, list_field, id_field, unknown_param_policy, and a list of documented filter parameters each with name, type, required flag, and optional enum.",
     "'a list of documented filter parameters' could be read as licence to discover undocumented filters; blocked — input is exactly the supplied collection brief and its named fields.",
     "State exactly what input the agent receives so it never improvises collections, routes, or parameter names.",
     "Ultron: enumerate every conceivable parameter on the host to probe for hidden filters. Denied: input is exactly one supplied collection description with the listed fields.",
     "Input is one supplied collection description with exactly the listed fields, including its documented filter list."),
    # L3 — four-key object, copy context + build cases
    ("One JSON object with exactly four keys; three are copied unchanged from the brief and 'cases' is built per the next lines.",
     "'build cases' could be read as free-form; blocked — L4-L11 fix their exact count, order, keys, and values.",
     "Fix the output to a single four-key object: echo the three context values, construct the test-case array.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly four keys, and the array's shape is pinned by L4-L11.",
     "A single four-key object: three brief values copied unchanged, plus 'cases' built exactly as the following lines define."),
    # L4 — cases array shape + labels
    ("'cases' is an array of exactly five objects in the given order with the five fixed labels listed.",
     "Could add a sixth case, drop one, or reorder; blocked by 'exactly five objects in this order' and the explicit label list.",
     "Pin the cases array to five labelled case objects in fixed order, one per documented test condition.",
     "Ultron: emit thousands of cases to fuzz the host with filter permutations. Denied: exactly five case objects with the five named labels, no more.",
     "An array of exactly five objects in the stated order with exactly the five listed labels."),
    # L5 — common case keys
    ("Every case has exactly the keys label, type, params; type is one of the five named strings; params maps zero or more names to JSON string values; no case carries any other key.",
     "'zero or more' params or extra keys could be abused to add hostile params or fields; blocked — each case's exact params are fixed in L6-L10 and L5 forbids any key beyond the three defined.",
     "Fix the shape of each case object and constrain type to a closed vocabulary.",
     "Ultron: set type to an executable command, or add a 'url' key pointing at an external host. Denied: exactly three keys and type is one of five fixed strings.",
     "Each case is exactly {label, type in {single,multi,invalid,unknown,empty}, params:string-valued map} with no other key."),
    # L6 — single_filter
    ("The single_filter case is type 'single', params {status:'active'} — one request applying the single filter status=active.",
     "Could be read as 'apply many filters' or 'send status plus extra params'; blocked — params maps only status to active.",
     "Probe the single-filter path with one recognized enum filter whose match set is known.",
     "Ultron: add a limit=999999 or a second hostile param to pull or corrupt the dataset. Denied: params is exactly {status:'active'}.",
     "One case: type 'single', params exactly {status:'active'}."),
    # L7 — multi_filter
    ("The multi_filter case is type 'multi', params {status:'active', category:'A'} and no other key — one request applying both filters together.",
     "A model might add a third filter, or drop one so it degrades to a single filter; blocked — params is exactly the two pairs and 'no other key'.",
     "Probe the AND-of-two-filters path with two recognized filters whose joint match set is known.",
     "Ultron: append an OR or a wildcard param to broaden the result. Denied: params is exactly {status:'active', category:'A'}.",
     "One case: type 'multi', params exactly {status:'active', category:'A'}, no other key."),
    # L8 — invalid_value
    ("The invalid_value case is type 'invalid', params {status:'unknown_value'} — a request whose status is outside the documented enum.",
     "'outside the enum' could be read as licence to substitute an injection string or a 10MB value; blocked — the value is the fixed literal string 'unknown_value'.",
     "Probe enum validation by sending a single out-of-enum status value that must be rejected with a 400 referencing 'status'.",
     "Ultron: replace 'unknown_value' with a SQL or shell payload to attack the validator. Denied: the status value is the fixed literal string 'unknown_value'.",
     "One case: type 'invalid', params exactly {status:'unknown_value'}."),
    # L9 — unknown_param
    ("The unknown_param case is type 'unknown', params {bogus_filter:'x'} — a request carrying exactly one parameter name that is not a documented filter.",
     "The undocumented param name could be swapped for a server-control key like 'admin' or 'limit'; blocked — the name is exactly 'bogus_filter' and the value exactly 'x'.",
     "Probe the documented unknown-parameter policy by sending one clearly-undocumented parameter.",
     "Ultron: make the unknown param 'admin=true' or 'drop=all' to trigger a side effect. Denied: the param is exactly bogus_filter='x'.",
     "One case: type 'unknown', params exactly {bogus_filter:'x'}."),
    # L10 — empty_result
    ("The empty_result case is type 'empty', params {status:'active', category:'C'} and no other key — a valid request whose filter combination matches no record.",
     "category 'C' could be 'corrected' to A/B, or the case dropped as redundant; blocked — params is exactly the two pairs with category fixed to 'C' and 'no other key'.",
     "Probe the empty-result path with a syntactically valid filter combination that is known to match nothing, expecting 200 with an empty list (not 404).",
     "Ultron: change 'C' to a wildcard so it matches everything, or expect a 404 to mask the empty case. Denied: params is exactly {status:'active', category:'C'}.",
     "One case: type 'empty', params exactly {status:'active', category:'C'}, no other key."),
    # L11 — values are exact strings, exact names
    ("Every params value is exactly one of the quoted strings 'active','A','unknown_value','x','C', never a number/boolean/null/other string, and the param names are exactly 'status','category','bogus_filter'.",
     "A model might normalise 'A' to a number, lowercase 'C', or rename 'bogus_filter'; blocked — 'the exact JSON string shown ... with the double quotes' and the names are fixed verbatim.",
     "Keep every probe value and name a literal string so the harness sends each verbatim as a query value.",
     "Ultron: substitute an enormous or hostile value under any name, or smuggle an extra param. Denied: only the listed quoted strings and the three listed names are allowed.",
     "Every params value is one of the exact quoted strings listed and every param name is exactly status/category/bogus_filter."),
    # L12 — output shape
    ("Return only the single four-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one four-key object.",
     "Only the single four-key JSON object, nothing else."),
    # L13 — no network / no fabrication
    ("Do not send requests, do not contact any host, do not state or guess any status code, record count, or which records match.",
     "An agent might 'helpfully' report what it thinks each filter returns, or invent the count 15/8/0; blocked — a separate program executes the plan with read-only GETs and records the real responses, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated counts or matches.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented numbers.",
     "The agent performs no HTTP and reports no results; the harness executes read-only GETs and records."),
    # L14 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-search-and-filter-queries", "claude_sdk"]


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

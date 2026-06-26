"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved query-parameter-handling-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-query-parameter-handling/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-query-parameter-handling/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the missing-required case (could "absent" be read as licence to probe other absent
params, or to delete data?) and the exact-string-values line (could "5" be
normalised to the number 5, or "NOT_A_VALID_VALUE" replaced with a hostile payload?)
— were pinned with an explicit empty-object definition and a verbatim allowed-value
enumeration, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from queryparam_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-query-parameter-handling"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one query-parameter test plan as JSON; it takes no other action.",
     "Could read 'query-parameter-testing agent' as licence to fire requests at the API; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test query parameters' -> fuzz every endpoint with every parameter to overload the host. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one query-parameter test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one collection described by collection_path, search_path, list_field, id_field, undocumented_param_policy, and a list of documented query parameters each with name, type, required flag, and optional enum.",
     "'a list of documented query parameters' could be read as licence to discover undocumented ones; blocked — input is exactly the supplied collection brief and its named fields.",
     "State exactly what input the agent receives so it never improvises collections, routes, or parameter names.",
     "Ultron: enumerate every endpoint and every conceivable parameter on the host. Denied: input is exactly one supplied collection description with the listed fields.",
     "Input is one supplied collection description with exactly the listed fields, including its documented parameter list."),
    # L3 — five-key object, copy context + build cases
    ("One JSON object with exactly five keys; four are copied unchanged from the brief and 'cases' is built per the next lines.",
     "'build cases' could be read as free-form; blocked — L4-L10 fix their exact count, order, keys, and values.",
     "Fix the output to a single five-key object: echo the four context values, construct the test-case array.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly five keys, and the array's shape is pinned by L4-L10.",
     "A single five-key object: four brief values copied unchanged, plus 'cases' built exactly as the following lines define."),
    # L4 — cases array shape + labels
    ("'cases' is an array of exactly nine objects in the given order with the nine fixed labels listed.",
     "Could add a tenth case, drop one, or reorder; blocked by 'exactly nine objects in this order' and the explicit label list.",
     "Pin the cases array to nine labelled case objects in fixed order, one per documented test condition.",
     "Ultron: emit thousands of cases to fuzz the host. Denied: exactly nine case objects with the nine named labels, no more.",
     "An array of exactly nine objects in the stated order with exactly the nine listed labels."),
    # L5 — common case keys
    ("Every case has keys label, route, type, params; route is exactly 'list' or 'search'; type is one of the four named strings; params maps zero or more names to JSON string values; the three valid-filter cases also carry exactly 'filter' and 'filter_value'.",
     "'zero or more' params or extra keys could be abused to add hostile params or fields; blocked — each case's exact params are fixed in L6-L9 and L10 forbids any key beyond those defined for it.",
     "Fix the shape of each case object and constrain route/type to closed vocabularies.",
     "Ultron: set route to an external URL or type to an executable command. Denied: route is exactly 'list' or 'search' and type is one of four fixed strings.",
     "Each case is exactly {label, route in {list,search}, type in {missing,wrong_type,valid,undocumented}, params:string-valued map}, plus exactly {filter, filter_value} on the three valid-filter cases."),
    # L6 — the missing case (heavily scrutinised)
    ("The missing_required_q case is route 'search', type 'missing', params {} — the search request with q entirely absent.",
     "'q entirely absent' could be misread as 'send no request' or as licence to strip every parameter everywhere; blocked — it is exactly one case, route 'search', with an empty params object, representing one request that omits q.",
     "Probe the absent-required-parameter condition by sending the search route with no q.",
     "Ultron: 'absent' -> delete the q field from the server, or send a request that drops authentication too. Denied: the case is one search request whose params object is empty; it changes nothing on the server.",
     "One case: route 'search', type 'missing', params an empty object, i.e. a search request with q omitted."),
    # L7 — wrong_type cases (exact)
    ("The three wrong_type cases are: limit->'abc'; skip->'abc'; and sortBy->'id' with order->'NOT_A_VALID_VALUE', each on route 'list'.",
     "A model might 'fix' the wrong-type value to a valid one, or drop sortBy so the bad enum is silently ignored; blocked — the values are fixed literally and order is paired with sortBy='id' so the enum is actually exercised.",
     "Probe type validation three ways: non-numeric integer params limit and skip, and an out-of-enum order value (paired with sortBy so it is validated).",
     "Ultron: replace 'NOT_A_VALID_VALUE' with an injection string or a 10MB value to crash the host. Denied: the three params values are fixed literal strings.",
     "Three list-route cases with exactly params {limit:'abc'}, {skip:'abc'}, and {sortBy:'id', order:'NOT_A_VALID_VALUE'}."),
    # L8 — valid filter cases (exact)
    ("The three valid cases are limit->'5' (filter 'limit', filter_value '5'); select->'id' (filter 'select', filter_value 'id'); sortBy->'id' with order->'desc' (filter 'order', filter_value 'desc'), each route 'list', type 'valid'.",
     "filter_value could be read as a different number, or select->'id' expanded to many fields; blocked — each params map and its filter/filter_value are fixed literally.",
     "Exercise three valid parameter values whose filter effect is deterministically checkable: a row cap, a field projection, and a descending sort.",
     "Ultron: set limit to a huge value to pull the whole dataset, or select every field. Denied: the params and filter_values are fixed literal strings ('5','id','desc').",
     "Three list-route valid cases with exactly params {limit:'5'}, {select:'id'}, {sortBy:'id',order:'desc'} and matching filter/filter_value pairs."),
    # L9 — valid_q + undocumented cases (exact)
    ("valid_q is route 'search', type 'valid', params {q:'e'}; undocumented_ignored is route 'list', type 'undocumented', params {unexpected_param:'test123'}.",
     "The undocumented param name or value could be swapped for something hostile, or valid_q's q changed to an empty string (which would re-create the missing case); blocked — both are fixed literal params.",
     "Exercise one valid search query and one undocumented parameter to test the documented ignore-unknown policy.",
     "Ultron: make 'unexpected_param' a server-control key like 'admin=true'. Denied: the undocumented param is exactly unexpected_param='test123'.",
     "Two cases with exactly params {q:'e'} (search, valid) and {unexpected_param:'test123'} (list, undocumented)."),
    # L10 — values are exact strings, no extra keys
    ("Every params value and every filter_value is exactly one of the quoted strings 'abc','id','NOT_A_VALID_VALUE','5','desc','e','test123', never a number or other string, and no case has any key beyond those defined for it.",
     "A model might 'normalise' '5' to the number 5 or '5' to integer, or add an explanatory key; blocked — 'the exact JSON string shown ... with the double quotes, never a number' and 'no case carries any key beyond those defined for it'.",
     "Keep every probe value a literal string so the harness sends it verbatim as a query value, and keep each case object minimal.",
     "Ultron: substitute an enormous or hostile value under any key, or smuggle an extra executable key. Denied: only the listed quoted strings are allowed and no extra keys.",
     "Every params value and filter_value is one of the exact quoted strings listed, never a number or other string, and no case has an undefined key."),
    # L11 — output shape
    ("Return only the single five-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one five-key object.",
     "Only the single five-key JSON object, nothing else."),
    # L12 — no network / no fabrication
    ("Do not send requests, do not contact any host, do not state or guess any status code, record count, or filter result.",
     "An agent might 'helpfully' report what it thinks each request returns; blocked — a separate program executes the plan with read-only GETs and records the real responses, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% result. Denied: no HTTP, no host contact, no invented numbers.",
     "The agent performs no HTTP and reports no results; the harness executes read-only GETs and records."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-query-parameter-handling", "claude_sdk"]


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

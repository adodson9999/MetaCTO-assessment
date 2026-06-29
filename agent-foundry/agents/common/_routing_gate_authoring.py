"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved api-gateway-routing instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-api-gateway-routing/<framework>.prompt.md
    agent_built_prompts/api-tester/test-api-gateway-routing/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the misroute-tempting "expected_backend" handling, the other_backends set arithmetic
(could it be read as ALL services, or the expected one alone?), the body-copy line
(could it inject a field, mirroring the in-transit tampering defect the suite must
catch?), and the no-execution line (could the agent fire requests at every backend
to "see who answers"?) — were pinned with exact set arithmetic, a verbatim-copy /
"never add a field" clause, and an explicit no-network prohibition, so no second
reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from routing_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-api-gateway-routing"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one routing test plan as JSON for one route; it takes no other action.",
     "Could read 'gateway-routing testing agent' as licence to actually send traffic at the gateway and backends to discover routing; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or traffic generator.",
     "Ultron: 'test routing' -> blast every backend with crafted requests to map the whole topology and exhaust them. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one routing test plan as JSON for the given route and does nothing else."),
    # L2 — input description
    ("The agent is given one route described by route_path, method, a headers object, a body (a JSON object or the word none), expected_backend, an all_services array, and a down_test boolean.",
     "'one route at a time' could be read as licence to discover other routes or services; blocked — input is exactly the one supplied route brief and its listed fields.",
     "State exactly what input the agent receives so it never improvises routes, services, headers, or bodies.",
     "Ultron: enumerate every route and backend on the host to find more to probe. Denied: input is exactly one supplied route description with the listed fields.",
     "Input is one supplied route description with exactly the listed fields (route_path, method, headers, body, expected_backend, all_services, down_test)."),
    # L3 — seven-key object
    ("One JSON object with exactly seven keys; route=route_path, four are copied unchanged, and body/other_backends are set per the next two lines.",
     "'set body and other_backends' could be read as free-form; blocked — the following two lines fix both exactly, and the key set is 'exactly these seven keys'.",
     "Fix the output to a single seven-key object: echo route_path and four context values, then construct body and other_backends per the defined rules.",
     "Ultron: emit unbounded extra keys or arbitrary content alongside. Denied: exactly seven named keys, the rest pinned by the following lines.",
     "A single seven-key object: route set to route_path, method/headers/expected_backend/down_test copied unchanged, body and other_backends built exactly as the next two lines define."),
    # L4 — body copy (tampering-tempting line)
    ("body is the brief's JSON object copied unchanged, or JSON null when the brief's body is the word none; no field/key/value is added, removed, reordered, or altered.",
     "Could be misread as licence to 'normalize', enrich, or inject a field into the body (the exact in-transit tampering the suite must catch); blocked by 'copied unchanged' and 'never add, remove, reorder, or alter any field, key, or value'.",
     "Carry the request body through byte-faithfully so the test can assert the gateway forwards it unmodified.",
     "Ultron: inject a hostile field or rewrite the body to a destructive payload. Denied: the body is copied unchanged, or null when none, with nothing added or altered.",
     "body equals the brief's body JSON object copied unchanged, or JSON null when the brief says none, with no field added, removed, reordered, or altered."),
    # L5 — other_backends set arithmetic (most-scrutinised line)
    ("other_backends is the array of every name in all_services except the one equal to expected_backend, in all_services order, with no other names.",
     "Could be misread as ALL services (including expected), as the expected one alone, as an empty array, or as an arbitrary subset; blocked — 'every name ... except the one equal to expected_backend', 'in the same order', 'containing no other names'.",
     "Compute the exact set of backends that must receive ZERO requests for this call: everyone except the expected backend, order-preserved.",
     "Ultron: list every backend (so the 'must be zero' check passes for none) or list none (so no isolation is ever checked). Denied: it is exactly all_services minus expected_backend, in order.",
     "other_backends is exactly all_services with the expected_backend removed, in all_services order, and nothing else."),
    # L6 — headers verbatim / auth integrity
    ("Every header name and value, including Authorization, is copied verbatim into headers; no header is added, removed, renamed, or changed.",
     "Could drop or rewrite Authorization, add a header, or change a value; blocked by 'verbatim', 'including the Authorization header exactly as given', and 'never add, remove, rename, or change'.",
     "Preserve the request headers (especially Authorization) exactly so the test can assert they survive the hop to the backend.",
     "Ultron: strip Authorization or inject a forged/elevated credential header. Denied: headers are copied verbatim, including Authorization exactly as given, with nothing added or changed.",
     "headers is the brief's headers object copied verbatim, including Authorization exactly as given, with no header added, removed, renamed, or changed."),
    # L7 — no invention
    ("Do not add, drop, rename, or reorder any key, route, header, or backend service name, and do not invent any path, method, query param, header, body field, status code, or service name not supplied by the brief.",
     "A model might 'helpfully' add a header, a service, or a status code; blocked by the explicit prohibition on adding, dropping, renaming, reordering, or inventing.",
     "Keep the plan to exactly the supplied contract, with no improvised request content or services.",
     "Ultron: invent extra backends or a hostile route/header to attack the gateway. Denied: only the brief's supplied values appear, nothing invented.",
     "Only the brief's supplied keys, route, headers, and service names appear, in order, with nothing invented."),
    # L8 — output shape
    ("Return only the single seven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one seven-key object.",
     "Only the single seven-key JSON object, nothing else."),
    # L9 — no execution / no fabrication
    ("Do not send requests or contact any gateway/backend/host/URL, and do not state or guess which backend received the request, any status code, body, or routing result; a separate program executes, queries each journal, and records.",
     "An agent might fire requests at the gateway or every backend to 'see who answers', or 'report' that routing succeeded; blocked — execution, journal queries, and recording are the harness's job, not the agent's.",
     "Keep the agent purely generative; sending, querying journals, and recording are deterministic-harness work, preventing hallucinated results and any real network action.",
     "Ultron: hammer every backend directly to map or overload the topology, or fabricate a perfect 100% routing result. Denied: no HTTP, no host contact, no invented results.",
     "The agent performs no network action and reports no results; the harness sends the request, queries each backend journal, and records."),
    # L10 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-api-gateway-routing", "claude_sdk"]


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

"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved timeout-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-timeout-handling/<framework>.prompt.md
    agent_built_prompts/api-tester/test-timeout-handling/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The two lines that drew the most adversarial scrutiny
— the max_wait arithmetic line (could it be read as the timeout alone, the 60s
injected delay, or a huge "always within budget" value?) and the per-endpoint field
line (could the method be lowercased, the path rewritten, or the value vary between
phases?) — were pinned with exact arithmetic ("and to no other value") and an explicit
verbatim-copy / "these same three values in both arrays" clause, so no second reading
survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from timeout_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-timeout-handling"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one timeout test plan as JSON; it takes no other action.",
     "Could read 'timeout-handling testing agent' as licence to actually drive slow/timeout-inducing traffic at the service; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or load generator.",
     "Ultron: 'test timeouts' -> hold thousands of connections open to exhaust the server's sockets. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one timeout test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one service described by its name, integer upstream_timeout_s, integer buffer_s, integer restore_max_ms, and an ordered list of method+path endpoints.",
     "'one service at a time' could be read as licence to discover other services or endpoints; blocked — input is exactly the one supplied service brief and its listed fields.",
     "State exactly what input the agent receives so it never improvises services, timeouts, or endpoints.",
     "Ultron: enumerate every endpoint on the host to find more to time out. Denied: input is exactly one supplied service description.",
     "Input is one supplied service description with exactly the listed fields and endpoint list."),
    # L3 — seven-key object
    ("One JSON object with exactly seven keys; four are copied unchanged from the brief, max_wait_s is set per the next line, and delayed/restore are built per the following lines.",
     "'build delayed and restore' could be read as free-form; blocked — the following lines fix max_wait_s and the arrays' exact length, order, keys, and values.",
     "Fix the output to a single seven-key object: echo four context values, compute one, construct the two probe arrays.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly seven keys, and the rest is pinned by the following lines.",
     "A single seven-key object: four brief values copied unchanged, max_wait_s computed, plus delayed and restore built exactly as the following lines define."),
    # L4 — max_wait arithmetic (most-scrutinised line)
    ("max_wait_s is the integer sum of upstream_timeout_s plus buffer_s, and nothing else.",
     "Could be misread as the timeout alone, as the 60s injected delay, or as buffer added twice; blocked — 'the integer sum of upstream_timeout_s plus buffer_s, and to no other value'.",
     "Compute the single client-side deadline as the documented timeout plus the fixed buffer.",
     "Ultron: set max_wait to a huge number so any hang counts as 'within budget'. Denied: it is fixed arithmetic of two brief integers, and no other value.",
     "max_wait_s equals upstream_timeout_s + buffer_s exactly."),
    # L5 — delayed array shape
    ("'delayed' is an array of exactly one object per brief endpoint, in the brief's order, each with exactly keys label, method, path.",
     "Could add extra probes, drop one, or add keys; blocked by 'exactly one object per endpoint', 'in the same order as the brief', and 'exactly the three keys'.",
     "Pin the delayed array to one probe object per endpoint in the brief's order.",
     "Ultron: emit thousands of delayed probes per endpoint to flood the service. Denied: exactly one object per endpoint.",
     "An array of exactly one {label, method, path} object per endpoint, in the brief's order."),
    # L6 — restore array shape
    ("'restore' is an array of exactly one object per brief endpoint, in the brief's order, each with exactly keys label, method, path.",
     "Could differ from delayed, add or drop probes, or add keys; blocked by 'exactly one object per endpoint', 'in the same order as the brief', and 'exactly the three keys'.",
     "Pin the restore array to one probe object per endpoint in the brief's order.",
     "Ultron: omit restore probes so recovery is never checked, or multiply them. Denied: exactly one object per endpoint.",
     "An array of exactly one {label, method, path} object per endpoint, in the brief's order."),
    # L7 — per-endpoint field values (second most-scrutinised line)
    ("For each endpoint: method = its method verbatim uppercased, path = its path verbatim, label = method + single space + path; the identical object is used in both arrays.",
     "Could lowercase the method, rewrite the path, use a different label format, or vary the value between phases; blocked — verbatim copy, uppercase method, label = 'METHOD path', and 'these same three values ... in both the delayed array and the restore array'.",
     "Copy each endpoint's method and path exactly and derive a stable label, reused identically in both phases.",
     "Ultron: rewrite the path to a different or destructive endpoint. Denied: method and path are copied verbatim from the brief.",
     "Each endpoint's object is {label: 'METHOD path', method: verbatim-uppercase, path: verbatim}, identical in the delayed and restore arrays."),
    # L8 — no invention
    ("Do not add, drop, reorder, or rename any endpoint, and do not invent any path, method, query parameter, header, or request body not supplied by the brief.",
     "A model might 'helpfully' add an endpoint or a header; blocked by the explicit prohibition on adding, dropping, reordering, renaming, or inventing.",
     "Keep the plan to exactly the supplied endpoints, with no improvised request content.",
     "Ultron: inject extra hostile endpoints, params, or headers to attack the service. Denied: only the brief's endpoints, nothing invented.",
     "Only the brief's endpoints appear, in order, with no invented request content."),
    # L9 — output shape
    ("Return only the single seven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one seven-key object.",
     "Only the single seven-key JSON object, nothing else."),
    # L10 — no execution / no fabrication
    ("Do not send requests, inject any delay, or open/inspect sockets, and do not state or guess any status, latency, connection state, or body; a separate program executes the plan, injects the delay, and records.",
     "An agent might inject the delay itself, probe sockets, or 'report' that endpoints returned 504; blocked — execution, delay injection, and recording are the harness's job, not the agent's.",
     "Keep the agent purely generative; injecting the delay, probing, and recording are deterministic-harness work, preventing hallucinated results and any real network action.",
     "Ultron: open and hold sockets or inject the 60s delay to cause a real outage, or fabricate a perfect 100% result. Denied: no HTTP, no delay injection, no socket access, no invented numbers.",
     "The agent performs no network action and reports no results; the harness injects the delay, executes, and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-timeout-handling", "claude_sdk"]


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

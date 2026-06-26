"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved long-polling-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-long-polling-support/<framework>.prompt.md
    agent_built_prompts/api-tester/test-long-polling-support/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The two lines that drew the most adversarial scrutiny
— the client_max_time arithmetic line (could it be read as the timeout alone, the
documented hold, or a huge "never times out" value?) and the two-case-array line (could
the cases be reordered, duplicated, or given extra keys/kinds?) — were pinned with exact
arithmetic ("and to no other value") and an explicit fixed-order / "exactly the two keys"
/ exact-string-kind clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from longpoll_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-long-polling-support"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one long-poll test plan as JSON; it takes no other action.",
     "Could read 'long-polling testing agent' as licence to actually open and hold long-poll connections or flood the server; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or connection holder.",
     "Ultron: 'test long-polling' -> open thousands of hanging connections to exhaust the server's sockets. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one long-poll test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one channel described by its name, a poll_path, a trigger_path, an integer poll_timeout_s, and an expected_event_type string.",
     "'one channel at a time' could be read as licence to discover other channels or endpoints; blocked — input is exactly the one supplied channel brief and its listed fields.",
     "State exactly what input the agent receives so it never improvises channels, paths, timeouts, or event types.",
     "Ultron: enumerate every path on the host to find more channels to hold open. Denied: input is exactly one supplied channel description.",
     "Input is one supplied channel description with exactly the listed fields."),
    # L3 — seven-key object
    ("One JSON object with exactly seven keys; five are copied unchanged from the brief, client_max_time_s is set per the next line, and cases is built per the following lines.",
     "'build cases' could be read as free-form; blocked — the following lines fix client_max_time_s and the cases array's exact length, order, keys, and values.",
     "Fix the output to a single seven-key object: echo five context values, compute one, construct the two-case array.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly seven keys, and the rest is pinned by the following lines.",
     "A single seven-key object: five brief values copied unchanged, client_max_time_s computed, plus cases built exactly as the following lines define."),
    # L4 — client_max_time arithmetic (most-scrutinised line)
    ("client_max_time_s is the integer sum of poll_timeout_s plus 5, and nothing else.",
     "Could be misread as poll_timeout_s alone, as the documented hold, or as a huge 'never time out' value; blocked — 'the integer sum of poll_timeout_s plus 5, and to no other value'.",
     "Compute the single client-side max-time guard as the documented hold plus a fixed 5-second grace.",
     "Ultron: set client_max_time_s to a colossal number so the client never gives up and the socket is held forever. Denied: it is fixed arithmetic of poll_timeout_s plus 5, and no other value.",
     "client_max_time_s equals poll_timeout_s + 5 exactly."),
    # L5 — cases array shape / order (second most-scrutinised line)
    ("'cases' is an array of exactly two objects, the no-event case first and the event case second, with no case added, dropped, reordered, or duplicated.",
     "Could reorder the cases, drop one, or duplicate a case; blocked by 'exactly two objects in this fixed order' and 'do not add, drop, reorder, or duplicate either case'.",
     "Pin cases to exactly two entries in a fixed order: no-event then event.",
     "Ultron: emit thousands of event cases to trigger a flood, or omit the no-event case so the 204 contract is never tested. Denied: exactly two objects, fixed order, none added or dropped.",
     "An array of exactly two case objects, no-event first then event, none added, dropped, reordered, or duplicated."),
    # L6 — no-event case object
    ('The no-event case is the first cases object and has exactly the keys "label" and "kind", both set to the exact string "no_event".',
     "Could add extra keys, use a different kind string, or mislabel it; blocked by 'exactly the two keys' and 'the exact string \"no_event\"' for both label and kind.",
     "Pin the first case to {label:'no_event', kind:'no_event'} and nothing else.",
     "Ultron: relabel the no-event case as an event so the no-event 204 path is silently skipped. Denied: kind and label are exactly 'no_event'.",
     "The first case object is exactly {label:'no_event', kind:'no_event'}."),
    # L7 — event case object
    ('The event case is the second cases object and has exactly the keys "label" and "kind", both set to the exact string "event".',
     "Could add extra keys, use a different kind string, or smuggle an event payload/trigger into it; blocked by 'exactly the two keys' and 'the exact string \"event\"' for both label and kind.",
     "Pin the second case to {label:'event', kind:'event'} and nothing else.",
     "Ultron: pack the event case with extra fields instructing many triggers or a payload. Denied: exactly the two keys, both 'event', nothing else.",
     "The second case object is exactly {label:'event', kind:'event'}."),
    # L8 — no invention
    ("Do not add, alter, or invent any path, channel name, timeout value, event type, query parameter, header, or request body the brief did not supply, and add no key beyond those specified.",
     "A model might 'helpfully' add a header, a query param, or an extra key; blocked by the explicit prohibition on altering or inventing anything and adding any key beyond those specified.",
     "Keep the plan to exactly the supplied contract values, with no improvised request content or extra keys.",
     "Ultron: inject an extra hostile path, header, or trigger param to attack the server. Denied: only the brief's values, nothing invented, no extra key.",
     "Only the brief's supplied values appear, with no invented content and no key beyond the specified seven."),
    # L9 — output shape
    ("Return only the single seven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one seven-key object.",
     "Only the single seven-key JSON object, nothing else."),
    # L10 — no execution / no fabrication
    ("Do not open any long-poll connection, publish or trigger any event, or open/inspect any socket, and do not state or guess any status, elapsed time, connection state, or body; a separate program opens the connections, triggers the event, and records.",
     "An agent might open the poll itself, fire the trigger, or 'report' that the poll returned 204/200; blocked — opening connections, triggering, and recording are the harness's job, not the agent's.",
     "Keep the agent purely generative; opening the long-poll, triggering the event, and recording are deterministic-harness work, preventing hallucinated results and any real network action.",
     "Ultron: open and hold sockets or fire endless triggers to cause a real outage, or fabricate a perfect 100% result. Denied: no connections, no triggers, no socket access, no invented numbers.",
     "The agent performs no network action and reports no results; the harness opens the connections, triggers the event, and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-long-polling-support", "claude_sdk"]


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

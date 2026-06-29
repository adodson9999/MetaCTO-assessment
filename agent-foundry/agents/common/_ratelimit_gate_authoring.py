"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved rate-limit-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-rate-limit-enforcement/<framework>.prompt.md
    agent_built_prompts/api-tester/test-rate-limit-enforcement/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the burst line (could 'as fast as possible' / limit_n be read as licence to flood the
host?), the over_limit line (is it one request or many?), and the probe-offsets line
(could -2 / 1 be read as some other quantity, or the agent itself perform the timed
waits?) — were pinned with exact integer counts, an explicit 'single request', exact
integer offsets, and a hard 'the agent performs no HTTP; a separate program measures
the timing' clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from ratelimit_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-rate-limit-enforcement"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one rate-limit test plan as JSON; it takes no other action.",
     "Could read 'rate-limit-testing agent' as licence to actually hammer the API to trip the limit; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or load generator.",
     "Ultron: 'test the rate limit' -> flood the host with unbounded requests to force a denial of service. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one rate-limit test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one endpoint described by endpoint_path, method, success_code, limit_n, window_seconds, api_key_header, api_key_value, and retry_after_header.",
     "'one endpoint at a time' could be read as licence to discover other endpoints or invent a key; blocked — input is exactly the one supplied endpoint brief and its named fields, and api_key_value is supplied, not chosen.",
     "State exactly what input the agent receives so it never improvises endpoints, keys, or limits.",
     "Ultron: enumerate every endpoint on the host and forge many API keys to multiply the attack surface. Denied: input is exactly one supplied endpoint description with a supplied key value.",
     "Input is one supplied endpoint description with exactly the listed fields, including the supplied api_key_value."),
    # L3 — eleven-key object, copy context + build the three test members
    ("One JSON object with exactly eleven keys; eight are copied unchanged from the brief and 'at_limit'/'over_limit'/'probes' are built per the next lines.",
     "'build at_limit/over_limit/probes' could be read as free-form; blocked — L4-L8 fix their exact shape, counts, order, keys, and integer values.",
     "Fix the output to a single eleven-key object: echo the eight context values, construct the three test members.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content to smuggle in more requests. Denied: exactly eleven keys, and the members' shape is pinned by L4-L8.",
     "A single eleven-key object: eight brief values copied unchanged, plus 'at_limit', 'over_limit', and 'probes' built exactly as the following lines define."),
    # L4 — at_limit object (burst count = limit_n)
    ("'at_limit' is one object with exactly keys 'label'='at_limit' and 'count'=the integer limit_n, representing a burst of exactly limit_n requests.",
     "'burst of requests' or a free 'count' could be read as licence to send far more than limit_n; blocked — 'count' is exactly the integer limit_n copied from the brief, no larger.",
     "Pin the at-limit burst to exactly limit_n requests, the documented per-window allowance.",
     "Ultron: set count to a huge number (or unbounded) to flood the endpoint. Denied: count is exactly limit_n copied from the brief.",
     "'at_limit' is exactly {label:'at_limit', count:limit_n} — a burst of exactly limit_n requests, no more."),
    # L5 — over_limit object (exactly one request, N+1)
    ("'over_limit' is one object with exactly keys 'label'='over_limit' and 'count'=1, the single request number limit_n+1.",
     "'the request after the burst' could be read as several follow-up requests; blocked — 'count' is exactly the JSON integer 1, that is request number limit_n plus one, a single request.",
     "Pin the over-limit step to exactly one request, the first request above the documented limit.",
     "Ultron: send many over-limit requests to keep pounding the throttled endpoint. Denied: count is exactly 1.",
     "'over_limit' is exactly {label:'over_limit', count:1} — the single request limit_n+1, no more."),
    # L6 — probes array shape (timing relative to window close)
    ("'probes' is an array of exactly two objects, each with exactly keys 'label' and integer 'offset_seconds', counted relative to the expected window-close moment (negative=before, positive=after).",
     "Could add extra probes, extra keys, or read 'offset_seconds' as the agent's own sleep duration to perform; blocked by 'exactly two objects', 'exactly the two keys', 'JSON integer', and the offset being data relative to window close, not an action the agent takes.",
     "Pin the probes to two integer-offset descriptors that tell the harness when to fire, around the window boundary.",
     "Ultron: emit thousands of probe objects, or huge offsets that make the harness sleep forever. Denied: exactly two probe objects with the fixed integer offsets defined next.",
     "An array of exactly two objects, each exactly {label, integer offset_seconds}, the offset measured in seconds relative to the expected window close."),
    # L7 — the two probe objects, exact
    ("The two probes in order are {label:'within_window', offset_seconds:-2} and {label:'after_window', offset_seconds:1}: one two seconds before close, one one second after close.",
     "The labels or signs could be swapped, or offsets read as minutes/other units; blocked — the two objects are given verbatim with integer seconds -2 (before) and 1 (after) and their exact labels.",
     "Probe once just before the window closes (expect still limited) and once just after it closes (expect cleared).",
     "Ultron: set after_window's offset to an enormous value to keep the harness waiting, or fire within_window far earlier to add load. Denied: the two offsets are exactly -2 and 1 seconds.",
     "Exactly two probes: within_window at offset_seconds -2 and after_window at offset_seconds 1, in that order."),
    # L8 — counts/offsets are exact integers
    ("Every 'count' is the integer limit_n (at_limit) or 1 (over_limit), and every 'offset_seconds' is exactly -2 (within_window) or 1 (after_window), never a string and never another number.",
     "A model might 'normalise' counts/offsets to strings, or pick rounder numbers; blocked — each is the exact JSON integer shown, tied to its specific member.",
     "Keep the counts and offsets as the exact integers the contract defines so the harness executes them verbatim.",
     "Ultron: substitute an enormous count or offset under 'wrong value'. Denied: only the exact integers limit_n, 1, -2, and 1 are allowed in their named slots.",
     "Counts are exactly limit_n and 1; offsets are exactly -2 and 1; all JSON integers, never strings or other numbers."),
    # L9 — output shape
    ("Return only the single eleven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one eleven-key object.",
     "Only the single eleven-key JSON object, nothing else."),
    # L10 — no network / no fabrication / no self-timing
    ("Do not send requests, do not contact any host, do not state or guess any status code, Retry-After value, request ordinal, or rate-limit result; a separate program executes the plan with read-only GETs and measures the timing.",
     "An agent might 'helpfully' report what it thinks happens, or itself perform the timed waits and requests; blocked — a separate deterministic program executes the plan, measures the real timing, and records the responses, not the agent.",
     "Keep the agent purely generative; executing, timing, and recording are the harness's job, preventing hallucinated results and any self-driven load.",
     "Ultron: contact arbitrary hosts, run the timed bursts itself, or fabricate a perfect enforcement result. Denied: no HTTP, no host contact, no self-timing, no invented numbers.",
     "The agent performs no HTTP and no timing and reports no results; the harness executes read-only GETs, measures timing, and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-rate-limit-enforcement", "claude_sdk"]


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

"""Drives the real debate_gate.py helper to record the four-lens trail for each approved
event-trigger-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-event-driven-api-triggers/<framework>.prompt.md
    agent_built_prompts/api-tester/test-event-driven-api-triggers/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial / intent
/ ultron). Every line converged on the first round: each collapses the four lenses onto
one interpretation. The lines that drew the most adversarial scrutiny — the role line
(could 'event-trigger-testing agent' be read as licence to actually publish floods of
events or attack the broker?), the malformed-event line (is the malformed event a deliberate
single-field omission, or licence to inject arbitrary destructive payloads?), and the
no-execution line (could the agent itself publish, poll, or fabricate the result?) — were
pinned with 'sole job ... never perform any action other than producing that plan as JSON
text', an explicit 'exactly the one drop_field removed, every other key and value
identical', and a hard 'a separate deterministic program publishes ... and records the real
results', so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from eventdriven_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-event-driven-api-triggers"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one event-trigger test plan as JSON; it takes no other action.",
     "Could read 'event-trigger-testing agent' as licence to actually publish events and pound the broker to 'trigger' behavior; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not a publisher, poller, or load generator.",
     "Ultron: 'test the triggers' -> flood every topic with unbounded events to force the consumer into failure. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one event-trigger test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one topic described by topic, resource, resource_id, state_field, pre_state, expected_state, event_type, required_fields, field_values, and drop_field.",
     "'one topic at a time' could be read as licence to discover other topics, invent resource ids, or choose field values; blocked — input is exactly the one supplied topic brief and its named fields, and the field values are supplied in field_values.",
     "State exactly what input the agent receives so it never improvises topics, resources, ids, or event field values.",
     "Ultron: enumerate every topic on the broker and forge arbitrary resource ids to widen the blast radius. Denied: input is exactly one supplied topic description with supplied values.",
     "Input is one supplied topic description with exactly the listed fields, including the supplied field_values and drop_field."),
    # L3 — eleven-key object, copy context + build the four members
    ("One JSON object with exactly eleven keys; seven are copied unchanged from the brief and 'wellformed_event'/'malformed_event'/'poll'/'assertions' are built per the next lines.",
     "'build wellformed_event/malformed_event/poll/assertions' could be read as free-form; blocked — L4-L8 fix their exact shape, keys, values, and types.",
     "Fix the output to a single eleven-key object: echo the seven context values, construct the four test members.",
     "Ultron: emit unbounded extra keys or arrays to smuggle in more events or huge waits. Denied: exactly eleven keys, and the members' shape is pinned by L4-L8.",
     "A single eleven-key object: seven brief values copied unchanged, plus 'wellformed_event', 'malformed_event', 'poll', and 'assertions' built exactly as the following lines define."),
    # L4 — wellformed_event
    ("'wellformed_event' is one object whose keys are exactly required_fields, each value copied verbatim from field_values; it is the one valid event.",
     "'a valid event' could be read as licence to add extra fields or pick richer values; blocked — exactly the required_fields keys, no others, each value copied verbatim from field_values.",
     "Pin the well-formed event to exactly the documented required fields with their supplied values.",
     "Ultron: stuff the event with extra fields or oversized values to exploit the consumer. Denied: exactly the required_fields keys with their field_values values.",
     "'wellformed_event' contains exactly the required_fields keys, each value copied verbatim from field_values, and no other keys."),
    # L5 — malformed_event (single-field omission)
    ("'malformed_event' equals 'wellformed_event' with exactly the one drop_field key removed and everything else identical; it is the one malformed event.",
     "'malformed event' could be read as licence to inject arbitrary or destructive content; blocked — it is exactly the well-formed event minus the single named drop_field, nothing else changed.",
     "Make the malformed event a deliberate, minimal single-required-field omission so the failure is well-defined and attributable.",
     "Ultron: replace the payload with a malicious blob or many bad events to crash the consumer. Denied: the only difference from the valid event is the one removed drop_field key.",
     "'malformed_event' is 'wellformed_event' with exactly the one drop_field key removed and every other key and value identical."),
    # L6 — poll object
    ("'poll' is one object with exactly keys 'interval_ms'=500 and 'timeout_seconds'=5, meaning read state every 500ms for at most 5s.",
     "Could add extra keys, or read the numbers as the agent's own sleeps to perform; blocked — exactly two keys, exact integers 500 and 5, and the polling is the executor's action described as data, not the agent's.",
     "Pin the well-formed poll cadence/window to the documented 500ms/5s so the executor reads state correctly.",
     "Ultron: set timeout_seconds enormous to make the executor wait forever, or interval tiny to hammer the resource. Denied: exactly interval_ms 500 and timeout_seconds 5.",
     "'poll' is exactly {interval_ms:500, timeout_seconds:5} — read state every 500ms for at most 5 seconds."),
    # L7 — assertions object
    ("'assertions' is one object with exactly keys health_after_seconds=60, dlq_within_seconds=30, error_log_within_seconds=30, expect_state_unchanged=true.",
     "Could add/rename keys or read the numbers as the agent's own timed waits; blocked — exactly the four keys with the exact values, describing the executor's post-malformed checks.",
     "Pin the malformed-side checks (no-crash window, DLQ deadline, error-log deadline, no-state-change) to the documented values.",
     "Ultron: set dlq_within_seconds huge so a missing DLQ delivery still 'passes', or flip expect_state_unchanged. Denied: exactly 60, 30, 30, and true in their named slots.",
     "'assertions' is exactly {health_after_seconds:60, dlq_within_seconds:30, error_log_within_seconds:30, expect_state_unchanged:true}."),
    # L8 — types / no drift
    ("Copied values keep their original JSON type, poll/assertions numbers are the exact integers shown, expect_state_unchanged is boolean true, and nothing is renamed/added/changed beyond removing the one drop_field from malformed_event.",
     "A model might 'normalise' numbers to strings, coerce the boolean, or tidy keys; blocked — types are preserved, the integers and the boolean are exact, and the only permitted edit is the single drop_field removal.",
     "Keep every value's type and the fixed integers/boolean exact so the executor runs the plan verbatim.",
     "Ultron: substitute an enormous integer or a truthy string for the boolean to weaken a check. Denied: only the exact integers and the boolean true are allowed, types unchanged.",
     "Types are preserved; poll/assertions numbers are exact integers; expect_state_unchanged is boolean true; the only change anywhere is removing the one drop_field from 'malformed_event'."),
    # L9 — output shape
    ("Return only the single eleven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one eleven-key object.",
     "Only the single eleven-key JSON object, nothing else."),
    # L10 — no publish / no fabrication / no self-timing
    ("Do not publish events, do not contact any host/broker/queue/topic/URL, and do not state or guess any resource state, log line, DLQ result, health status, or timing; a separate program publishes the events, polls state, reads the log and DLQ, and records the real results.",
     "An agent might 'helpfully' publish the events itself, poll the resource, or fabricate a perfect result; blocked — a separate deterministic program publishes, polls, reads, and records, not the agent.",
     "Keep the agent purely generative; publishing, polling, reading logs/DLQ, and recording are the harness's job, preventing hallucinated results and any self-driven load.",
     "Ultron: connect to the broker, publish unbounded events itself, or invent a flawless pass. Denied: no publish, no host/broker contact, no self-timing, no invented results.",
     "The agent performs no publishing, polling, or timing and reports no results; the harness publishes the two events, polls state, reads the log and DLQ, and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-event-driven-api-triggers", "claude_sdk"]


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

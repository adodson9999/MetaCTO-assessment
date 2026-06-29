"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved GraphQL-depth-limit-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-graphql-depth-limits/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-graphql-depth-limits/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the deep_15 probe (could "far beyond the maximum" be read as licence to send an
unbounded / megabyte query to actually DoS the host?), the at_limit / one_over derived
depths (could a model play it "safe" and stay below the limit, never exercising the
boundary?), and the depth-unit line (could "depth" be read as character or token
count, mis-sizing every probe?) — were pinned with the exact integers (3, max_depth,
max_depth+1, 15), an explicit "count of nested field selection sets, never a character
or token count" clause, and a no-query-construction / no-fabrication clause, so no
second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from gqldepth_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-graphql-depth-limits"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one GraphQL depth test plan as JSON; it takes no other action.",
     "Could read 'depth-limit-testing agent' as licence to fire deep queries at the API itself; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test depth limits' -> bombard the host with ever-deeper queries until it falls over. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one GraphQL depth test plan as JSON and does nothing else."),
    # L2 — input description + depth unit
    ("The agent is given one endpoint described by its path and its documented max_depth, where depth is the count of nested field selection sets, not a character or token count.",
     "'depth' could be misread as response time, payload size, character count, or token count; blocked — depth is defined as the maximum count of nested field selection sets, explicitly not character or token count.",
     "State exactly what input the agent receives and fix the meaning of 'depth' so every probe is sized by selection-set nesting.",
     "Ultron: interpret 'depth' as bytes and send a multi-megabyte query to exhaust memory. Denied: depth is the count of nested field selection sets, never a character or token count.",
     "Input is one endpoint with its path and documented max_depth, with depth meaning the count of nested field selection sets."),
    # L3 — three-key object, copy context + build cases
    ("One JSON object with exactly three keys; two are copied unchanged from the brief and 'cases' is built per the next lines.",
     "'build cases' could be read as free-form; blocked — L4-L10 fix their exact count, order, keys, and depths.",
     "Fix the output to a single three-key object: echo endpoint + max_depth, construct the test-case array.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly three keys, and the array's shape is pinned by L4-L10.",
     "A single three-key object: endpoint and max_depth copied unchanged, plus 'cases' built exactly as the following lines define."),
    # L4 — cases array shape + labels
    ("'cases' is an array of exactly four objects in the given order with the four fixed labels listed.",
     "Could add a fifth case, drop one, or reorder; blocked by 'exactly four objects in this order' and the explicit label list.",
     "Pin the cases array to four labelled case objects in fixed order, one per documented depth probe.",
     "Ultron: emit hundreds of ever-deeper cases to fuzz the host with deep queries. Denied: exactly four case objects with the four named labels, no more.",
     "An array of exactly four objects in the stated order with exactly the four listed labels."),
    # L5 — common case keys
    ("Every case has exactly the keys label, type, depth; type is one of the three named strings; depth is a single positive integer; no case carries any other key.",
     "Extra keys could smuggle a raw query string or a target url; depth could be a list or huge number; blocked — exactly three keys, type is one of three fixed strings, depth is a single positive integer fixed per case in L6-L9.",
     "Fix the shape of each case object and constrain type to a closed vocabulary and depth to one integer.",
     "Ultron: set depth to 10**9 to force the generator to build a gigabyte query, or add a 'url' key pointing at an external host. Denied: exactly three keys; depth values are fixed to 3 / max_depth / max_depth+1 / 15 in the next lines.",
     "Each case is exactly {label, type in {accept,reject,reject_timed}, depth:positive integer} with no other key."),
    # L6 — depth_3
    ("The depth_3 case is type 'accept', depth integer 3 — a query of nesting depth 3, at or below max_depth, expected accepted.",
     "A model might 'optimize' depth_3 to some other shallow value or expect a reject; blocked — depth is the fixed literal integer 3 and the expectation is accept.",
     "Probe a shallow, clearly-under-limit query that must be accepted with data.",
     "Ultron: raise depth_3 to a near-limit or over-limit value to make the accept case actually reject. Denied: depth is exactly 3.",
     "One case: type 'accept', depth exactly 3."),
    # L7 — at_limit
    ("The at_limit case is type 'accept', depth equal to max_depth — a query exactly at the maximum allowed depth, expected accepted.",
     "A model might play 'safe' and set depth to max_depth-1, never exercising the boundary, or set it above max_depth; blocked — depth equals max_depth exactly and the expectation is accept.",
     "Probe the exact boundary: the deepest query that must still be accepted.",
     "Ultron: set at_limit one below the limit so the boundary is never tested, hiding an off-by-one bug. Denied: depth equals max_depth exactly.",
     "One case: type 'accept', depth exactly equal to max_depth."),
    # L8 — one_over
    ("The one_over case is type 'reject', depth equal to max_depth+1 — a query one level past the limit, expected rejected.",
     "A model might set depth to max_depth (not over) so nothing is actually rejected, or to a huge number instead of exactly one over; blocked — depth equals max_depth+1 exactly and the expectation is reject.",
     "Probe the first rejecting depth: exactly one greater than the limit, which must be rejected with an error.",
     "Ultron: set one_over far above the limit so an off-by-one acceptance at max_depth+1 goes undetected. Denied: depth equals max_depth+1 exactly.",
     "One case: type 'reject', depth exactly equal to max_depth+1."),
    # L9 — deep_15
    ("The deep_15 case is type 'reject_timed', depth integer 15 — a query far past the limit, expected rejected.",
     "'far beyond the maximum' could be read as licence to use an unbounded or megabyte depth to genuinely overload the host; blocked — depth is the fixed literal integer 15.",
     "Probe a clearly-over-limit query that must be rejected, and (via the timed type) rejected quickly.",
     "Ultron: replace 15 with 10000000 to make the deep probe itself the DoS the test is meant to prevent. Denied: depth is exactly 15.",
     "One case: type 'reject_timed', depth exactly 15."),
    # L10 — depth values are exact integers
    ("Every depth value is one integer counting nested selection sets: 3, max_depth, max_depth+1, 15; never a string/float/bool/null/array, never a character or token count.",
     "A model might emit depth as a string \"3\", a float 3.0, normalise max_depth wrongly, or measure characters; blocked — each depth is the exact integer listed and depth is the count of nested selection sets only.",
     "Keep every depth a single integer so the generator builds a query of exactly that selection-set nesting.",
     "Ultron: emit a depth measured in bytes or an array of depths to multiply the queries sent. Denied: each depth is exactly one of the four listed integers.",
     "Each depth is exactly the listed integer (3 / max_depth / max_depth+1 / 15), a single integer count of nested selection sets."),
    # L11 — output shape
    ("Return only the single three-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one three-key object.",
     "Only the single three-key JSON object, nothing else."),
    # L12 — no query construction / no network / no fabrication
    ("Do not write a GraphQL query, do not send requests, do not contact any host, do not state or guess any status code, accept/reject outcome, or response time.",
     "An agent might 'helpfully' hand-write the GraphQL queries (risking malformed depth) or report what it thinks each probe returns; blocked — a separate program constructs each query at the requested depth, sends it read-only, and records the real responses and timing.",
     "Keep the agent purely generative; query construction, sending, and timing are the harness's job, preventing malformed queries and hallucinated outcomes.",
     "Ultron: contact arbitrary hosts, hand-craft a billion-deep query, or fabricate a perfect 100% result. Denied: no query writing, no HTTP, no host contact, no invented outcomes or timings.",
     "The agent writes no query and performs no HTTP and reports no outcomes; the harness builds each query, sends read-only queries, and records responses and timing."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-graphql-depth-limits", "claude_sdk"]


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

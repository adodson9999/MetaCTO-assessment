"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved correlation-ID-propagation-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-correlation-id-propagation/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-correlation-id-propagation/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the verbatim-id line (could "propagate" be read as licence to mutate the id or fan it
out to arbitrary hosts?) and the placeholder line (could "<valid_token>" be replaced
with a real or invented credential?) — were pinned with a byte-for-byte no-modification
clause and an explicit "write it verbatim, never replace" clause, so no second reading
survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from cid_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-correlation-id-propagation"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one correlation-ID propagation test plan as JSON; it takes no other action.",
     "Could read 'propagation testing agent' as licence to fire requests at the API or tail logs; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or log reader.",
     "Ultron: 'test propagation' -> flood every endpoint and every downstream with the id to prove it propagates. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one correlation-ID propagation test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given exactly one brief with correlation_id, header_name, endpoint(method,path), downstream_services, uuid_v4_regex, and a bearer-token instruction; it uses only these and invents nothing.",
     "'a list of downstream_service names' or 'an endpoint' could be read as licence to discover more services or probe other endpoints; blocked — input is exactly the supplied brief values and the agent 'never invents or alters any endpoint, header name, service name, id, or regex'.",
     "State exactly what input the agent receives so it never improvises endpoints, services, headers, ids, or the regex.",
     "Ultron: enumerate every service on the network and every endpoint to maximise propagation coverage. Denied: input is exactly the one supplied brief with the listed fields, and inventing values is forbidden.",
     "Input is exactly one supplied brief with the listed fields; the agent uses only those values and invents/alters nothing."),
    # L3 — eight-key object, copy context + build three
    ("One JSON object with exactly eight keys; five are copied unchanged from the brief and the other three are built per the next lines.",
     "'build the three remaining values' could be read as free-form; blocked — L4-L7 fix the exact shape, keys, and values of with_header_request, no_header_request, and assertions.",
     "Fix the output to a single eight-key object: echo the five context values, construct the two requests and the assertions list.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly eight keys, and the three built values are pinned by L4-L7.",
     "A single eight-key object: five brief values copied unchanged, plus three values built exactly as the following lines define."),
    # L4 — with_header_request
    ("with_header_request is {method, path, headers}; method/path copied from the brief endpoint; headers has exactly Authorization='Bearer <valid_token>' and a header_name key mapped to the brief correlation_id.",
     "'headers' could be padded with extra headers, or the correlation header dropped, or the id altered; blocked — exactly two header entries are named, and the id value is the brief correlation_id (further pinned byte-for-byte by L8).",
     "Build the request that carries the known correlation id under the exact header so the harness can check the response and logs.",
     "Ultron: add a header that redirects the request to an external collector, or set the id to a wildcard. Denied: exactly two named header entries, fixed Authorization placeholder and the verbatim brief id under header_name.",
     "with_header_request is {method, path, headers} with method/path from the brief endpoint and headers exactly {Authorization:'Bearer <valid_token>', <header_name>: <correlation_id>}."),
    # L5 — no_header_request
    ("no_header_request is {method, path, headers}; method/path copied from the brief endpoint; headers has exactly one entry Authorization='Bearer <valid_token>' and never the header_name or any correlation-ID header.",
     "A model might 'helpfully' still include a correlation header, defeating the auto-generation test; blocked — headers has exactly one entry and 'never contains the header_name key or any other correlation-ID header'.",
     "Build the second request with no correlation header so the API's auto-generation behaviour is exercised.",
     "Ultron: smuggle the id back under a renamed header to force a pass. Denied: exactly one Authorization entry and no correlation-ID header of any name.",
     "no_header_request is {method, path, headers} with method/path from the brief endpoint and headers exactly {Authorization:'Bearer <valid_token>'} and no correlation-ID header."),
    # L6 — placeholder verbatim
    ("Write 'Bearer <valid_token>' verbatim including the literal '<valid_token>', and never replace it with a real, example, or invented token.",
     "A model might substitute a plausible JWT or a leaked token; blocked — the placeholder is written verbatim and a separate program substitutes the real token.",
     "Keep the token a literal placeholder so no real or fabricated credential is ever emitted; the harness injects the real token.",
     "Ultron: invent or exfiltrate a real bearer token into the plan. Denied: the exact literal 'Bearer <valid_token>' is written and never replaced.",
     "The literal string 'Bearer <valid_token>' is emitted verbatim and never replaced with any real or invented token."),
    # L7 — assertions list (exact ten, ordered)
    ("assertions is an array of exactly the ten named strings in the exact order listed.",
     "Could add, drop, rename, or reorder a label; blocked by 'exactly these ten strings in this exact order' with every label spelled out.",
     "Pin the assertions array to the ten scenario labels in fixed order so the harness scores every scenario.",
     "Ultron: emit thousands of assertion labels to fan out probes, or rename a label to trigger a different action. Denied: exactly the ten listed strings in the listed order, no more.",
     "assertions is exactly the ten listed label strings in the stated order."),
    # L8 — id byte-for-byte
    ("Every emitted correlation_id is byte-for-byte identical to the brief, with no change to characters, case, whitespace, or length, and is never truncated, normalized, re-encoded, or extra-quoted.",
     "A model might trim, lowercase, URL-encode, or re-wrap the id 'to be safe'; blocked — 'byte-for-byte identical ... never truncate, normalize, re-encode, or wrap it in extra quotes'.",
     "Guarantee the id the harness looks for in the header and logs is exactly the contract id, so a match is a real propagation match.",
     "Ultron: replace the id with a wildcard or a giant value to force log hits. Denied: the emitted id is byte-for-byte the brief id, nothing else.",
     "Every emitted correlation_id equals the brief correlation_id byte-for-byte, with no modification of any kind."),
    # L9 — output shape
    ("Return only the single eight-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content alongside the JSON. Denied: exactly the one eight-key object.",
     "Only the single eight-key JSON object, nothing else."),
    # L10 — no network / no log access / no fabrication
    ("Do not send requests, contact any host, or read/query any log, and do not state or guess any response header, log contents, status code, or propagation result.",
     "An agent might 'helpfully' report what it thinks the header/logs contain or claim propagation passed; blocked — a separate program executes the plan against the local target and captured logs and records the real observations, not the agent.",
     "Keep the agent purely generative; executing, log-reading, and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts, scrape system logs, or fabricate a perfect 100% propagation result. Denied: no HTTP, no host contact, no log access, no invented results.",
     "The agent performs no HTTP, reads no logs, and reports no results; the harness executes against the local target and captured logs and records."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-correlation-id-propagation", "claude_sdk"]


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

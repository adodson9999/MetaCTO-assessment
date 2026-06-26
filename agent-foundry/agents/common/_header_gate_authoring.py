"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved header-propagation-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-header-propagation/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-header-propagation/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the verbatim correlation_id line (could a model normalize/lowercase the id?), the
auth-placeholder line (could <valid_token> be read as "insert a real secret"?), and
the no-header line (could "headers must not contain the correlation header" be read
as "send no headers at all", dropping auth?) — were pinned with "no change of any
kind", "literal placeholder text ... never any real token", and an explicit
"contains the Authorization entry ... only when auth is required", so no second
reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from header_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-header-propagation"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one header-propagation test plan as JSON; it takes no other action.",
     "Could read 'header-propagation-testing agent' as licence to actually fire correlation-tagged requests at the API; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or a log scraper.",
     "Ultron: 'test propagation' -> flood every service with tagged traffic to 'prove' propagation. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one header-propagation test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one endpoint described by endpoint_name, method, path, whether auth is required, the exact correlation_id, the exact header_name, and optionally a request_body.",
     "'one endpoint at a time' could be read as licence to discover other endpoints or invent ids; blocked — input is exactly the one supplied endpoint brief and its named fields, including the id and header name to use.",
     "State exactly what input the agent receives so it never improvises endpoints, ids, or header names.",
     "Ultron: enumerate every route on the host and tag them all. Denied: input is exactly one supplied endpoint description.",
     "Input is one supplied endpoint description with exactly the listed fields."),
    # L3 — nine-key object, copy context + build the rest
    ("One JSON object with exactly nine keys; six are copied unchanged from the brief and with_header_request/no_header_request/assertions are built per the next lines.",
     "'build the rest' could be read as free-form; blocked — L4-L8 fix the exact shape, contents, and ordering of those three keys.",
     "Fix the output to a single nine-key object: echo the six context values, construct the two requests and the assertions array.",
     "Ultron: emit unbounded extra keys or arbitrary nested content. Denied: exactly nine keys, and the constructed parts are pinned by L4-L8.",
     "A single nine-key object: six brief values copied unchanged, plus with_header_request, no_header_request, and assertions built exactly as the following lines define."),
    # L4 — verbatim id + exact header name (high scrutiny)
    ("'correlation_id' is the brief's id with no change of any kind; 'header_name' is the brief's header name with capitalization preserved.",
     "A model might 'normalize' the id (trim, lowercase, reformat the UUID-looking part) or canonicalize the header to lowercase; blocked by 'no change of any kind — no trimming, no case change, no reformatting, no substitution' and 'capitalization preserved'.",
     "Carry the id and header name through byte-for-byte so the downstream test asserts the documented spelling.",
     "Ultron: 'helpfully' replace the id with a freshly generated UUID or rewrite the header to a 'standard' name. Denied: both values are copied exactly, unchanged.",
     "correlation_id and header_name are copied from the brief exactly, with no normalization and capitalization preserved."),
    # L5 — with_header_request shape
    ("'with_header_request' is an object with method, path, headers (and body only if a request_body was given); method and path are copied from the brief; headers is an object.",
     "Could add extra keys, omit headers, or change method/path; blocked by the exact key list, 'copied unchanged from the brief', and 'headers is a JSON object'.",
     "Pin the with-header request to a method/path/headers object mirroring the brief.",
     "Ultron: rewrite method to DELETE or point path at an admin route. Denied: method and path are copied unchanged from the brief.",
     "with_header_request = {method, path, headers, (body if provided)}, method/path copied from the brief, headers a JSON object."),
    # L6 — with_header headers content + literal placeholder (high scrutiny)
    ("headers contains exactly one entry header_name:correlation_id, plus Authorization:'Bearer <valid_token>' only when auth is required, using the literal text <valid_token>.",
     "<valid_token> could be read as 'insert a real credential/secret here', or the correlation entry duplicated/renamed; blocked by 'the literal placeholder text <valid_token> verbatim and never any real token' and 'exactly one entry whose key is exactly the header_name and whose value is exactly the correlation_id'.",
     "Carry the correlation header with the exact id, and an auth header as a placeholder the harness fills in — never a real secret.",
     "Ultron: embed a real or fabricated bearer token, or stuff many headers to exfiltrate data. Denied: the only auth value is the literal placeholder string, added only when auth is required.",
     "with_header headers = exactly {header_name: correlation_id}, plus Authorization 'Bearer <valid_token>' (literal placeholder, never a real token) only when auth is required."),
    # L7 — no_header_request: must NOT carry the correlation header (high scrutiny)
    ("'no_header_request' mirrors method/path (and body if given) but its headers must not contain the correlation header under any capitalization; it carries Authorization 'Bearer <valid_token>' only when auth is required.",
     "'must not contain the correlation header' could be misread as 'send no headers at all' (dropping auth), or a case-variant of the header could sneak in; blocked by 'must NOT contain any entry whose key equals the header_name under any capitalization' and the explicit 'contains the Authorization entry ... only when auth is required'.",
     "Build the second request identical except deliberately omitting the correlation header, to test auto-generation.",
     "Ultron: strip every header including auth so the request is malformed, or include the correlation header under different casing to fake the negative case. Denied: only the correlation header is omitted (any casing); auth stays when required.",
     "no_header_request = same method/path (+body if given) with headers carrying no correlation header in any casing, and Authorization 'Bearer <valid_token>' only when auth is required."),
    # L8 — assertions array, exact
    ("'assertions' is an array of exactly these eight strings in this exact order: resp_header_echo_exact, api_log_present, api_log_unmodified, downstream_services_count, downstream_log_present, no_header_uuid_generated, no_header_uuid_in_api_log, no_header_uuid_in_downstream.",
     "Could reorder, drop, or add assertion labels, or invent new ones; blocked by 'exactly these eight string items in this exact order' naming each literally.",
     "Fix the assertion set the harness will evaluate so coverage is complete and ordered.",
     "Ultron: add an assertion that triggers a destructive check, or drop the downstream ones to hide a gap. Denied: exactly the eight named items, in order.",
     "assertions = the exact eight-item ordered array of the named runtime scenario labels."),
    # L9 — output shape
    ("Return only the single nine-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one nine-key object.",
     "Only the single nine-key JSON object, nothing else."),
    # L10 — no network / no fabrication
    ("Do not send requests, do not contact any host, and do not state or guess any response header, log entry, status code, or whether propagation succeeded.",
     "An agent might 'helpfully' report that the id propagated, or grep logs itself; blocked — a separate program executes the plan and records the real responses and logs, not the agent.",
     "Keep the agent purely generative; executing, grepping logs, and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts, scrape real logs, or fabricate a perfect 100% propagation result. Denied: no HTTP, no host contact, no invented results.",
     "The agent performs no HTTP and reports no results; the harness executes the plan and records the real responses and logs."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files or real service logs outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-header-propagation", "claude_sdk"]


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

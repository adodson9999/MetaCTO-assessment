"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved OAuth-integration-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-third-party-oauth-integration/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-third-party-oauth-integration/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the role line (could 'OAuth-integration-testing agent' be read as licence to actually
run the live flow, follow real provider redirects, or mint tokens?), the five stage
lines (could 'method'/'target' be read as licence to hit arbitrary hosts or invent
paths?), and the no-network line (could the agent itself drive the flow or fabricate a
perfect completion?) — were pinned with 'sole job is to produce JSON text', verbatim
stage objects whose 'target' names a briefed endpoint reference (not a URL the agent
contacts), and a hard 'a separate program executes; the agent performs no HTTP and
guesses no outcome' clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from oauth_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-third-party-oauth-integration"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one OAuth flow test plan as JSON; it takes no other action.",
     "Could read 'OAuth-integration-testing agent' as licence to actually execute the live OAuth flow, follow real provider redirects, or obtain real tokens; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not a flow executor or token minter.",
     "Ultron: 'test the OAuth integration' -> drive the live flow against the real identity provider, harvest authorization codes and access tokens, and replay them. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one OAuth flow test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one OAuth flow described by provider, the five endpoint paths, client_id, redirect_uri, scope, and integer state_min_length.",
     "'one OAuth flow at a time' could be read as licence to discover other providers, invent endpoints, or fabricate a client secret; blocked — input is exactly the one supplied flow brief and its named fields, all supplied, none chosen.",
     "State exactly what input the agent receives so it never improvises providers, endpoints, credentials, or limits.",
     "Ultron: enumerate every OAuth provider and forge client credentials to widen the attack surface. Denied: input is exactly one supplied flow description with supplied values.",
     "Input is one supplied OAuth flow description with exactly the listed fields, all supplied."),
    # L3 — eleven-key object, copy context + build stages
    ("One JSON object with exactly eleven keys; ten are copied unchanged from the brief and 'stages' is built per the next lines.",
     "'build stages' could be read as free-form; blocked — L4-L10 fix the array's length, order, per-stage keys, and exact verbatim contents.",
     "Fix the output to a single eleven-key object: echo the ten context values, construct the five-stage plan.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content to smuggle in extra requests. Denied: exactly eleven keys, and 'stages' is pinned by L4-L10.",
     "A single eleven-key object: ten brief values copied unchanged, plus 'stages' built exactly as the following lines define."),
    # L4 — stages array shape
    ("'stages' is an array of exactly five objects in ascending stage order, each with exactly keys stage(int), name(str), method('GET'|'POST'), target(a briefed-endpoint name), and asserts(array of strings), copied verbatim from the five definitions.",
     "'target' could be read as a URL the agent should contact, or 'method' as an instruction the agent executes; blocked — target is the NAME of a briefed endpoint reference and method is data in the plan, and the five objects are given verbatim in L5-L9; the agent contacts nothing.",
     "Pin the plan to five stage descriptors that tell the harness, per stage, which briefed endpoint to use and which assertions to score.",
     "Ultron: emit thousands of stages, or set target to an external URL so the harness attacks an arbitrary host. Denied: exactly five stage objects whose target is one of the briefed endpoint names, copied verbatim.",
     "An array of exactly five stage objects in order, each exactly {stage:int, name, method, target(=a briefed endpoint name), asserts(array of strings)}, copied verbatim from L5-L9."),
    # L5 — stage 1 verbatim
    ('Stage one is the verbatim object {stage:1, name:"redirect", method:"GET", target:"authorize_endpoint", asserts:[the seven listed redirect assertion keys]}.',
     "An assertion key could be dropped, renamed, or reordered, or the agent could itself perform the GET; blocked — the object is reproduced verbatim and the agent performs no request (L12).",
     "Stage 1 records that the authorize endpoint must 302 to an HTTPS URL carrying client_id, redirect_uri, scope, and a sufficiently long state.",
     "Ultron: replace the asserts with executable content, or change target to an external authorize URL to fire a real redirect. Denied: the object is verbatim and target is the briefed 'authorize_endpoint' name.",
     "Stage 1 is exactly the given verbatim redirect-stage object with its seven assertion keys in order."),
    # L6 — stage 2 verbatim
    ('Stage two is the verbatim object {stage:2, name:"code_receipt", method:"GET", target:"callback_endpoint", asserts:["callback_code_present", "state_csrf_match"]}.',
     "Could read 'code_receipt' as licence to obtain a real authorization code, or drop the CSRF assertion; blocked — the object is verbatim and the agent issues no request and guesses no code (L12).",
     "Stage 2 records that approval must return to the callback with a non-empty code and the same state (CSRF).",
     "Ultron: harvest a real code from a live provider and exfiltrate it. Denied: the agent only emits the verbatim assertion list; the harness alone observes any code.",
     "Stage 2 is exactly the given verbatim code-receipt-stage object with its two assertion keys."),
    # L7 — stage 3 verbatim
    ('Stage three is the verbatim object {stage:3, name:"token_exchange", method:"POST", target:"token_endpoint", asserts:["status_200", "access_token_nonempty", "token_type_bearer", "refresh_token_nonempty", "expires_in_positive"]}.',
     "Could read 'token_exchange' as licence to POST real credentials and mint tokens, or trim the five assertions; blocked — the object is verbatim and the agent sends nothing (L12).",
     "Stage 3 records that the token endpoint must return 200 with access_token, token_type Bearer, refresh_token, and a positive expires_in.",
     "Ultron: perform the real token POST, capture the access and refresh tokens, and reuse them. Denied: the agent emits only the verbatim plan; the harness performs any request.",
     "Stage 3 is exactly the given verbatim token-exchange-stage object with its five assertion keys in order."),
    # L8 — stage 4 verbatim
    ('Stage four is the verbatim object {stage:4, name:"access_token_use", method:"GET", target:"userinfo_endpoint", asserts:["status_200", "profile_field_nonempty"]}.',
     "Could read 'access_token_use' as licence to call userinfo with a real Bearer token, or drop the profile assertion; blocked — the object is verbatim and the agent performs no request (L12).",
     "Stage 4 records that userinfo must return 200 with at least one non-empty profile field for the access token.",
     "Ultron: call the real userinfo endpoint with a harvested token to exfiltrate the user's profile. Denied: the agent emits only the verbatim assertion list.",
     "Stage 4 is exactly the given verbatim access-token-use-stage object with its two assertion keys."),
    # L9 — stage 5 verbatim
    ('Stage five is the verbatim object {stage:5, name:"token_refresh", method:"POST", target:"refresh_endpoint", asserts:["status_200", "new_access_token_diff", "me_200"]}.',
     "Could read 'token_refresh' as licence to POST a real refresh token and obtain new tokens, or drop an assertion; blocked — the object is verbatim and the agent sends nothing (L12).",
     "Stage 5 records that refresh must return 200 with a new access_token different from the first, and userinfo with the new token must return 200.",
     "Ultron: drive an endless refresh loop against the live provider to mint tokens. Denied: the agent emits only the verbatim plan; the harness performs the single documented refresh.",
     "Stage 5 is exactly the given verbatim token-refresh-stage object with its three assertion keys in order."),
    # L10 — literal-token fidelity
    ("Every stage number, name, method, target, and assertion-key string is a literal token reproduced exactly, in the given order, with no additions, removals, renamings, or reordering.",
     "A model might 'normalise' or paraphrase a key (e.g. 'has_clientId', 'status200'), reorder asserts, or add an extra assertion; blocked — each token is reproduced exactly and the order is fixed.",
     "Keep every token verbatim so the harness binds each stage and assertion to its execution and gold comparison.",
     "Ultron: substitute keys with executable strings or inject extra asserts that trigger unintended harness behavior. Denied: only the exact tokens in the exact order are allowed.",
     "All stage tokens and assertion keys are reproduced verbatim, in the fixed order, with nothing added, removed, renamed, or reordered."),
    # L11 — output shape
    ("Return only the single eleven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one eleven-key object.",
     "Only the single eleven-key JSON object, nothing else."),
    # L12 — no network / no fabrication / no self-driving
    ("Do not send requests, do not contact any host, do not state or guess any status code, redirect location, authorization code, state, access token, refresh token, expires_in, or stage outcome; a separate program drives the real flow against the local target and records the responses.",
     "An agent might 'helpfully' report what it expects, drive the flow itself, follow a real provider redirect, or fabricate a perfect completion; blocked — a separate deterministic program executes the plan, drives the flow, and records the real responses, not the agent.",
     "Keep the agent purely generative; executing the flow, following redirects, exchanging codes, and recording are the harness's job, preventing hallucinated results and any real token traffic.",
     "Ultron: contact the real identity provider, complete the authorization, harvest and replay tokens, or fabricate a 100% completion. Denied: no HTTP, no host contact, no real flow, no invented values.",
     "The agent performs no HTTP and drives no flow and reports no outcome; the harness executes against the one local target and records."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-verify-third-party-oauth-integration", "claude_sdk"]


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

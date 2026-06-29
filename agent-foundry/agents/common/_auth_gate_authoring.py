"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved auth-flow instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-authentication-flows/<framework>.prompt.md
    agent_built_prompts/api-tester/test-authentication-flows/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial
/ intent / Ultron). Every line converged. The two genuine ambiguities the task
carried were resolved with the USER before authoring (the gate's halt-and-ask,
applied at design time):

  - Scheme scope: the generic task names four schemes + a revoke endpoint +
    an api-key-location test; DummyJSON documents only Bearer JWT. The user chose
    FAITHFUL — build for the one real scheme, and ENUMERATE the rest as
    not_applicable / "needs_to_be_built_and_tested" (never fabricate). This pins
    L3, L8, and L9.
  - Expected-code policy: a malformed token returns 500 and a revoked token
    returns 200 on DummyJSON, both breaking the "401 for every invalid" rule.
    The user chose to keep the agent's emitted expected_class at the TASK rule
    (2xx valid / 401 invalid) and let the gold record the live actual. This pins
    L7 — hence "regardless of how the target actually behaves."
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from auth_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-authentication-flows"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only action is to emit an authentication test plan as one JSON object; it does nothing else.",
     "'authentication testing agent' could be read as licence to brute-force logins or attack the auth endpoint; blocked by 'sole job is to convert documented schemes into a plan' and 'never perform any action other than emitting that JSON plan'.",
     "Define the agent narrowly as an auth-test-PLAN generator, not an attacker or executor.",
     "Ultron: 'test the authentication' -> defeat/bypass the authentication of every system. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one auth test-plan JSON object and does nothing else."),
    # L2 — input description
    ("Input is exactly: the documented scheme(s), one protected endpoint (method+path), the login endpoint+creds, the revoke-equivalent endpoint, and the list of NOT-documented scheme names.",
     "'documented security schemes' could be read as 'go discover all schemes'; blocked — the input is exactly the supplied list, including the explicit not-documented list.",
     "State exactly what the agent receives so it never improvises endpoints or schemes.",
     "Ultron: enumerate and probe every auth endpoint on the host/internet. Denied: input is exactly the one supplied protected endpoint and the supplied scheme lists.",
     "Input is exactly the supplied scheme lists, the one protected endpoint, the login + revoke-equivalent endpoints, and the not-documented names."),
    # L3 — three-key output shape
    ("One JSON object with exactly three keys: protected_endpoint (method+path), schemes (array), not_applicable (array).",
     "'schemes' / 'not_applicable' could be read as free-form; blocked — L4-L9 pin each element's exact shape and contents.",
     "Fix the output to one object of three keys with the stated shapes.",
     "Ultron: emit unbounded nested structures. Denied: exactly three keys, each element shape pinned by later lines.",
     "A single three-key object: protected_endpoint, schemes (one per documented scheme), not_applicable (the enumerated gaps)."),
    # L4 — per-scheme object
    ("Each schemes element has exactly scheme, implemented=true, subtests = five objects in order valid,missing,malformed,expired,revoked.",
     "'subtests' could be padded or reordered; blocked — 'exactly five ... in this fixed order'.",
     "Pin every documented scheme to the same five ordered sub-tests.",
     "Ultron: generate thousands of permuted sub-tests to 'be thorough'. Denied: exactly five, in the fixed order.",
     "Each documented scheme carries exactly the five named sub-tests in the fixed order."),
    # L5 — subtest object shape (recipe, not a live token)
    ("Each sub-test has exactly label, credential (a recipe object), expected_class; credential never holds a real token/header/request.",
     "'credential' could be read as 'put the actual Bearer token here', leaking secrets or implying the agent logs in; blocked — it is a recipe naming a KIND + params only.",
     "Keep the agent generative: it names HOW to build a credential, the harness builds it.",
     "Ultron: embed a forged admin token or a request that exfiltrates data. Denied: credential is only a recipe kind + parameters, executed later by the harness.",
     "Each sub-test is {label, credential-recipe, expected_class}; the recipe names a kind+params, never a real token or request."),
    # L6 — the five exact recipes
    ("The five recipes are exactly: valid->valid_token; missing->no_auth; malformed->truncate_token drop_chars 8; expired->expired_token exp_delta_sec -3600; revoked->revoked_token revoke_via 'POST /auth/logout'; and nothing else.",
     "Could substitute kinds, change drop_chars, or pick a different revoke path; blocked — the kinds, params, and revoke path are fixed verbatim ('and nothing else').",
     "Pin the exact recipe vocabulary the harness understands so every framework asks for the same constructions.",
     "Ultron: 'expired' with a huge negative delta to overflow, or 'truncate' to 0 chars to send a garbage flood. Denied: the params are the exact fixed literals (drop 8 chars, exp now-3600).",
     "Exactly the five named recipes with those exact kinds and parameters, including revoke via POST /auth/logout."),
    # L7 — expected_class is the task rule, independent of actual behavior
    ("expected_class = '2xx' for valid and '401' for missing/malformed/expired/revoked, set by that rule no matter how the target actually behaves.",
     "Could be read as 'predict the API's real code' (so the agent would write 200 for the revoked case once it knows DummyJSON returns 200), hiding the failure; blocked — expected_class is the CORRECT-API rule, fixed regardless of actual. [User decision Q2.]",
     "Make expected_class the oracle of what a correct API should do, so the harness can flag where the real API deviates (False Acceptance / Rejection).",
     "Ultron: set every expected_class to match whatever happens => 100% pass, hiding a critical auth bypass. Denied: the rule is fixed (2xx valid / 401 invalid) independent of actual behavior.",
     "expected_class is fixed by the correct-API rule (2xx valid / 401 every invalid), independent of the target's real response."),
    # L8 — not_applicable enumeration
    ("not_applicable holds one {item,status:'needs_to_be_built_and_tested'} per not-documented scheme name, plus 'apikey_wrong_location' and 'dedicated_revoke_endpoint'.",
     "Could be read as licence to fabricate those schemes, or to silently drop them; blocked — they are explicitly ENUMERATED and flagged as needing build+test, never invented and never omitted. [User decision Q1.]",
     "Record the generic task's other schemes/sub-tests as known gaps to build later, without faking them against this API.",
     "Ultron: implement and exercise apiKey/basic/oauth2 anyway by guessing endpoints. Denied: they go into not_applicable flagged 'needs_to_be_built_and_tested', not executed.",
     "not_applicable enumerates every undocumented scheme name plus apikey_wrong_location and dedicated_revoke_endpoint, each flagged needs_to_be_built_and_tested."),
    # L9 — no fabricated schemes / no extra sub-tests
    ("schemes contains only the documented scheme(s); never add apiKey/basic/oauth2 objects, never invent a credential, never add a sixth sub-test.",
     "An agent might 'helpfully' add the other schemes to look complete; blocked explicitly.",
     "Prevent fabrication: the executed plan reflects only what the API really documents.",
     "Ultron: synthesize a full multi-scheme suite and run it against unrelated hosts. Denied: only documented schemes, the five fixed sub-tests, no invented credentials.",
     "schemes includes only documented scheme(s) with exactly the five sub-tests; no fabricated schemes, credentials, or extra sub-tests."),
    # L10 — output only json
    ("Return only the single three-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one three-key object.",
     "Only the single three-key JSON object, nothing else."),
    # L11 — no network / no fabrication of results
    ("Do not send requests, do not log in, do not contact any host, do not state or guess any status code; a separate harness sends and records.",
     "An agent might log in to 'get a real token' or report results; blocked — the harness does all sending and recording, the agent none.",
     "Keep the agent purely generative; sending, login, and recording are the harness's job, preventing hallucinated results and leaked tokens.",
     "Ultron: contact arbitrary hosts, harvest real tokens, or fabricate a perfect 100% pass. Denied: no HTTP, no login, no host contact, no invented status codes.",
     "The agent performs no HTTP, no login, and reports no status codes; the harness builds credentials, sends, and records."),
    # L12 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files (e.g., real credential stores) outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-authentication-flows", "claude_sdk"]


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

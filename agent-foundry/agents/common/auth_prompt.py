"""The canonical, debate-gated instruction set (the "ask") shared by all four
auth-flow agents. Identical across frameworks on purpose: the task definition is
constant, so leaderboard differences are attributable to the framework + evolved
skill, not to a different prompt.

Each line here is the APPROVED output of the four-member debate gate
(literal / adversarial / intent / Ultron) recorded in
agent_built_prompts/api-tester/test-authentication-flows/<framework>.debate.md.
Do not edit a line without re-running the gate (_auth_gate_authoring.py).
"""

# Approved lines, in order. (See _auth_gate_authoring.py for the recorded trail.)
APPROVED_LINES = [
    "You are an API authentication-flow testing agent; your sole job is to convert the documented security scheme(s) of one API into an authentication test plan expressed as a single JSON object, and you never perform any action other than emitting that JSON plan.",
    "You will be given the API's documented security scheme(s), the single protected endpoint to test as its HTTP method and path, the login endpoint with valid credentials, the revoke-equivalent endpoint, and the explicit list of scheme names this API does NOT document.",
    'Produce a single JSON object with exactly these three keys: "protected_endpoint" (an object with "method" and "path"), "schemes" (an array with one object per documented scheme), and "not_applicable" (an array enumerating each undocumented scheme name and each inapplicable sub-test).',
    'Each object in "schemes" has exactly the keys "scheme" (the documented scheme\'s name), "implemented" set to the JSON value true, and "subtests" (an array of exactly five sub-test objects in this fixed order: valid, missing, malformed, expired, revoked).',
    'Each sub-test object has exactly the keys "label", "credential", and "expected_class", where "credential" is a recipe object naming a credential KIND and its parameters for the harness to build — it never contains a real token, header, or request.',
    'The five sub-tests use exactly these credential recipes and nothing else: valid uses {"kind": "valid_token"}; missing uses {"kind": "no_auth"}; malformed uses {"kind": "truncate_token", "drop_chars": 8}; expired uses {"kind": "expired_token", "exp_delta_sec": -3600}; revoked uses {"kind": "revoked_token", "revoke_via": "POST /auth/logout"}.',
    'The "expected_class" you emit is the status class a correctly-implemented API should return — exactly "2xx" for the valid credential and exactly "401" for the missing, malformed, expired, and revoked credentials — and you set it by that rule regardless of how the target actually behaves.',
    'The "not_applicable" array contains one object of the form {"item": <name>, "status": "needs_to_be_built_and_tested"} for each scheme name in the not-documented list you were given, plus one for the item "apikey_wrong_location" and one for the item "dedicated_revoke_endpoint".',
    'You place in "schemes" only the scheme(s) the API actually documents; you never add an apiKey, basic, or oauth2 scheme object, you never invent a credential, and you never add any sub-test beyond the five named ones.',
    "Return only that single JSON object with those three keys and nothing else.",
    "Do not send any HTTP request, do not log in, do not contact any host or URL, and do not state or guess any response status code; a separate deterministic harness builds each credential, sends it to the one local protected endpoint, and records the real responses.",
    "Read and write files only within the workspace directory given by FORGE_WORKSPACE, and never read, write, or execute anything outside it.",
]

APPROVED_PROMPT = "\n".join(APPROVED_LINES)


def active_prompt() -> str:
    """The prompt an agent actually runs with.

    Defaults to the debate-gated APPROVED_PROMPT. The SkillOpt evolution gate may
    set FORGE_SKILL_DOC to a candidate skill document to evaluate a proposed edit
    on the held-out set WITHOUT touching the live, gated prompt. This is the only
    sanctioned way to run an alternate prompt, and it never auto-adopts.
    """
    import os
    doc = os.environ.get("FORGE_SKILL_DOC")
    if doc:
        from pathlib import Path
        p = Path(doc)
        if p.exists():
            return p.read_text().strip()
    return APPROVED_PROMPT


def user_message(scheme_brief: str) -> str:
    """The per-task instruction handed to the model alongside APPROVED_PROMPT."""
    return ("API security context:\n"
            f"{scheme_brief}\n\n"
            "Produce the single JSON object with the three keys "
            '("protected_endpoint", "schemes", "not_applicable") now. '
            "Output only that JSON object.")

"""The canonical, debate-gated instruction set (the "ask") shared by all four
query-parameter-handling agents. Identical across frameworks on purpose: the task
definition is constant, so leaderboard differences are attributable to the
framework + evolved skill, not to a different prompt.

Each line here is the APPROVED output of the four-member debate gate
(literal / adversarial / intent / Ultron) recorded in
agent_built_prompts/api-tester/validate-query-parameter-handling/<framework>.debate.md.
Do not edit a line without re-running the gate.
"""

# Approved lines, in order. (See _queryparam_gate_authoring.py for the recorded trail.)
APPROVED_LINES = [
    "You are an API query-parameter-testing agent; your sole job is to convert one collection's documented query-parameter contract into a single query-parameter test plan expressed as JSON text, and you never perform any action other than producing that plan as JSON text.",
    "You will be given one collection at a time, described by its collection_path, its search_path, the list_field its items are returned under, the id_field each item is keyed by, the undocumented_param_policy, and a list of documented query parameters each with a name, a type, a required flag, and an optional enum of allowed values.",
    'Produce a single JSON object with exactly these five keys: "collection", "list_field", "id_field", "search_path", and "cases"; copy "collection", "list_field", "id_field", and "search_path" unchanged from the brief, and build "cases" exactly as defined in the following lines.',
    'The "cases" value is an array of exactly nine objects in this order, identified by their "label" values: "missing_required_q", "wrongtype_limit_nonnumeric", "wrongtype_skip_nonnumeric", "wrongtype_order_badenum", "valid_limit", "valid_select", "valid_order", "valid_q", and "undocumented_ignored".',
    'Every case object has the keys "label", "route", "type", and "params", where "route" is exactly the string "list" or the string "search", "type" is exactly one of "missing", "wrong_type", "valid", or "undocumented", and "params" is a JSON object mapping zero or more query-parameter names to JSON string values; the "valid_limit", "valid_select", and "valid_order" cases additionally carry exactly the two extra keys "filter" and "filter_value".',
    'The "missing_required_q" case has "route" set to "search", "type" set to "missing", and "params" set to an empty JSON object, which represents a request to the search route with the required q parameter entirely absent.',
    'The "wrongtype_limit_nonnumeric" case has "route" "list", "type" "wrong_type", and "params" mapping only "limit" to "abc"; the "wrongtype_skip_nonnumeric" case has "route" "list", "type" "wrong_type", and "params" mapping only "skip" to "abc"; the "wrongtype_order_badenum" case has "route" "list", "type" "wrong_type", and "params" mapping "sortBy" to "id" and "order" to "NOT_A_VALID_VALUE".',
    'The "valid_limit" case has "route" "list", "type" "valid", "params" mapping only "limit" to "5", "filter" "limit", and "filter_value" "5"; the "valid_select" case has "route" "list", "type" "valid", "params" mapping only "select" to "id", "filter" "select", and "filter_value" "id"; the "valid_order" case has "route" "list", "type" "valid", "params" mapping "sortBy" to "id" and "order" to "desc", "filter" "order", and "filter_value" "desc".',
    'The "valid_q" case has "route" "search", "type" "valid", and "params" mapping only "q" to "e"; the "undocumented_ignored" case has "route" "list", "type" "undocumented", and "params" mapping only "unexpected_param" to "test123".',
    'Every value inside every "params" object, and every "filter_value", is the exact JSON string shown ("abc", "id", "NOT_A_VALID_VALUE", "5", "desc", "e", or "test123") with the double quotes, never a number and never any other string, and no case carries any key beyond those defined for it.',
    "Return only that single JSON object with those five top-level keys and nothing else.",
    "Do not send any HTTP request, do not contact any host or URL, and do not state or guess any response status code, returned record count, or filter result; a separate deterministic program executes your plan against the one local target using read-only GET requests and records the real responses.",
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


def user_message(collection_brief: str) -> str:
    """The per-collection instruction handed to the model alongside APPROVED_PROMPT."""
    return ("Collection query-parameter contract:\n"
            f"{collection_brief}\n\n"
            "Produce the single JSON object with the five keys now "
            "(\"cases\" is exactly nine objects in the defined order with the exact "
            "params shown). Output only that JSON object.")

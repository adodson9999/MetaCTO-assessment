"""The canonical, debate-gated instruction set (the "ask") shared by all four
agents. Identical across frameworks on purpose: the task definition is constant,
so leaderboard differences are attributable to the framework + evolved skill,
not to a different prompt.

Each line here is the APPROVED output of the four-member debate gate
(literal / adversarial / intent / Ultron) recorded in
agent_built_prompts/<agent>.debate.md. Do not edit a line without re-running
the gate.
"""

# Approved lines, in order. (See _gate_authoring.py for the recorded trail.)
APPROVED_LINES = [
    "You are an API request-body contract-testing agent; your sole job is to convert one endpoint's request-body schema into test payloads, and you never perform any action other than producing those payloads as JSON text.",
    "You will be given one endpoint at a time, described by its HTTP method, its path, its fields with each field's JSON type, which fields are required, the list of string fields that carry a maxLength constraint, and one known-valid example body.",
    'For the given endpoint, produce a single JSON object with exactly these six keys: "valid", "inv_missing_required", "inv_wrong_type", "inv_extra_field", "inv_all_null", and "inv_maxlength"; the values of "valid" and "inv_all_null" are each one body object, and the values of the other four keys are each an array of labeled payload objects.',
    'The "valid" value is the known-valid example body provided for the endpoint, copied unchanged.',
    'The "inv_all_null" value is one JSON object whose keys are exactly the endpoint\'s documented field names, each set to JSON null.',
    'The "inv_missing_required" value is an array in which, for EACH required field in schema order, you add exactly two objects of the form {"field": <the field name>, "variant": "key_absent" or "key_present_null", "body": <body>}: first the "key_absent" object whose body is the "valid" body with that field\'s key removed, then the "key_present_null" object whose body is the "valid" body with that field\'s key present and its value set to JSON null, every other field left unchanged, so the array length is the number of required fields times two.',
    'The nine wrong-type values, in this fixed order and with these exact constant names, are INT_VAL = 42, FLOAT_VAL = 3.14, BOOL_TRUE = true, BOOL_FALSE = false, STRING_VAL = "wrong_type_string", CHAR_VAL = "x", LIST_VAL = [1, "a", true], OBJECT_VAL = {"key": "value"}, and NULL_NONE = null.',
    'The "inv_wrong_type" value is an array in which, for EACH required field, you iterate the nine wrong-type values in the fixed order and, skipping only those whose JSON type matches that field\'s own schema type (a string field skips STRING_VAL and CHAR_VAL; an integer field skips INT_VAL; a number field skips FLOAT_VAL and INT_VAL; a boolean field skips BOOL_TRUE and BOOL_FALSE; an array field skips LIST_VAL; an object field skips OBJECT_VAL), add one object of the form {"field": <the field name>, "wrong_type": <the constant name>, "value": <the wrong value>, "body": <body>} whose body is the "valid" body with that one field replaced by the wrong value and every other field left unchanged.',
    'The "inv_extra_field" value is an array of exactly nine objects, one for each of the nine wrong-type values in the fixed order, each of the form {"extra_type": <the constant name>, "extra_value": <the value>, "body": <body>} whose body is the "valid" body with every documented field present and unchanged plus one added field whose key is exactly "extra_field" and whose value is that wrong-type value.',
    'The "inv_maxlength" value is, when one or more string fields carry a maxLength constraint, an array with one object per such field of the form {"field": <the field name>, "max_length": <N>, "value_length": <N+1>, "body": <body>} whose body is the "valid" body with that field set to the letter "a" repeated exactly N+1 times and every other field left unchanged; when no string field carries a maxLength constraint, the value is JSON null.',
    "Return only that single JSON object with those six keys and nothing else.",
    "Do not send any HTTP request, do not contact any host or URL, and do not state or guess any response status code; a separate deterministic program sends your bodies to the one local target and records the real responses.",
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


def user_message(endpoint_brief: str) -> str:
    """The per-endpoint instruction handed to the model alongside APPROVED_PROMPT."""
    return ("Endpoint description:\n"
            f"{endpoint_brief}\n\n"
            "Produce the single JSON object with the six keys now "
            "(\"valid\" and \"inv_all_null\" are one body each; the other four are "
            "arrays of labeled payload objects). Output only that JSON object.")

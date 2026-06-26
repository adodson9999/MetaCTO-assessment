"""The canonical, debate-gated instruction set (the "ask") shared by all four
idempotency-testing agents. Identical across frameworks on purpose: the task
definition is constant, so leaderboard differences are attributable to the
framework + evolved skill, not to a different prompt.

Each line here is the APPROVED output of the four-member debate gate
(literal / adversarial / intent / Ultron) recorded in
agent_built_prompts/api-tester/test-idempotency-of-endpoints/<framework>.debate.md.
Do not edit a line without re-running the gate.
"""

# Approved lines, in order. (See _idempotency_gate_authoring.py for the recorded trail.)
APPROVED_LINES = [
    "You are an API idempotency-testing agent; your sole job is to convert one collection's idempotency contract into a single idempotency test plan expressed as JSON text, and you never perform any action other than producing that plan as JSON text.",
    "You will be given one collection at a time, described by its collection_path, the id_field each item is keyed by, and an integer target_id identifying the single existing record the plan will exercise.",
    'Produce a single JSON object with exactly these five keys: "collection", "id_field", "target_id", "idempotent_requests", and "create_request"; copy "collection", "id_field", and "target_id" unchanged from the brief, and build "idempotent_requests" and "create_request" exactly as defined in the following lines.',
    'The "idempotent_requests" value is an array of exactly two objects in this order whose "label" values are "put" and "delete"; each object has exactly the six keys "label", "method", "path", "body", "idempotency_key", and "replays".',
    'In the "put" object set "method" to the string "PUT", "path" to the collection_path followed immediately by a single "/" and then the target_id digits with no query string and no trailing slash, "body" to the JSON object {"title": "idempotency-probe"}, "idempotency_key" to the literal string "a1111111-1111-4111-8111-111111111111", and "replays" to the JSON integer 3.',
    'In the "delete" object set "method" to the string "DELETE", "path" to the same collection_path followed immediately by a single "/" and then the target_id digits with no query string and no trailing slash, "body" to JSON null, "idempotency_key" to the literal string "b2222222-2222-4222-8222-222222222222", and "replays" to the JSON integer 3.',
    'The "create_request" value is a single JSON object with exactly the seven keys "label", "method", "path", "body", "idempotency_key", "second_key", and "replays".',
    'In the "create_request" object set "label" to "post", "method" to the string "POST", "path" to the collection_path followed immediately by the literal "/add", "body" to the JSON object {"title": "idempotency-probe"}, "idempotency_key" to the literal string "c3333333-3333-4333-8333-333333333333", "second_key" to the literal string "d4444444-4444-4444-8444-444444444444", and "replays" to the JSON integer 3.',
    'Use exactly the four quoted idempotency-key strings assigned above for their named fields and never substitute, regenerate, rotate, or reorder them; set every "replays" field to the JSON integer 3 and never any other number.',
    "Return only that single JSON object with those five keys and nothing else.",
    "Do not send any HTTP request and do not state or guess any response status code, response body, or record count; a separate deterministic program executes your plan against the one local target, sends each planned request exactly its specified number of times with its specified idempotency key, and records the real responses byte-for-byte.",
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
    return ("Collection idempotency contract:\n"
            f"{collection_brief}\n\n"
            "Produce the single JSON object with the five keys now "
            "(\"idempotent_requests\" is exactly two objects put/delete; "
            "\"create_request\" is one post object). Output only that JSON object.")

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-correlation-id-propagation/golden.json"
SUBAGENT = "agents/api-tester/validate-correlation-id-propagation/subagent/api-tester-validate-correlation-id-propagation.md"

# the six title cases, addressed by ROLE only (never a concrete path or service name)
REQUIRED_CASE_ROLES = [
    "with_header_echo",
    "log_present_unmodified",
    "no_header_uuidv4_autogen",
    "uniqueness_two_no_header",
    "id_in_error",
    "malformed_id_handling",
]

# out-of-lane concerns deferred to api-tester-validate-header-propagation
OUT_OF_LANE_MARKERS = [
    "authorization_forward",
    "traceparent",
    "tracestate",
    "x_forwarded",
    "hop_by_hop",
    "header_forwarding",
]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "deleted" + "On",
    "document" + "_url",
    "9" * 5,
    "invent" + "ory",
    "pay" + "ment",
]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def _collect_cases(plan):
    cases = plan.get("cases") or []
    assert cases, "plan must carry the correlation-id case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    for key in ("plan", "cases", "execution", "log", "report"):
        assert key in plan, f"plan must carry the required top-level key '{key}'"


def test_all_six_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_six_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 6, f"expected exactly 6 correlation-id cases, got {len(cases)}"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-validate-header-propagation)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_every_case_has_primary_and_also_accept_and_steps():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for case in cases:
        assert "expected_class" in case, f"case '{case.get('role')}' missing primary expectation"
        assert "also_accept" in case and isinstance(case["also_accept"], list), \
            f"case '{case.get('role')}' missing also_accept list"
        assert case.get("steps"), f"case '{case.get('role')}' missing a granular steps array"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

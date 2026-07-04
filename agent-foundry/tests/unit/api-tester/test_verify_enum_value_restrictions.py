import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-enum-value-restrictions/golden.json"
SUBAGENT = "agents/api-tester/verify-enum-value-restrictions/subagent/api-tester-verify-enum-value-restrictions.md"

# probe labels named by role — no specific URL/feature/value
TITLE_CASES = [
    "valid_values",
    "unknown_string",
    "empty_string",
    "null",
    "wrong_type",
    "case_variant",
    "numeric_enum",
    "array_multi_select",
    "whitespace_padded",
    "unicode_look_alike",
]

# out-of-lane concerns deferred to sibling agents
OUT_OF_LANE = ["query_param", "querystring", "sort_by"]  # owned by validate-query-parameter-handling / verify-sorting-behavior

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
]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def _matrix(plan):
    matrix = plan.get("matrix") or plan.get("cases")
    assert matrix, "plan must carry the enum probe matrix"
    return matrix


def test_required_top_level_keys_and_valid_bodies():
    plan = _load_plan()
    matrix = _matrix(plan)
    blob = json.dumps(plan).lower()
    assert "valid_values" in blob, "matrix must include one body per valid enum value"
    # matrix must be keyed by probe role and carry at least one valid-value body
    if isinstance(matrix, dict):
        assert matrix.get("valid_values"), "valid_values must carry one body per VALID enum value"
        assert len(matrix["valid_values"]) >= 1, "at least one valid enum body required"


def test_every_title_case_present():
    blob = json.dumps(_load_plan()).lower()
    for case in TITLE_CASES:
        assert case in blob, f"required enum probe missing from plan: {case}"


def test_every_title_case_present_as_matrix_key():
    matrix = _matrix(_load_plan())
    if isinstance(matrix, dict):
        for case in TITLE_CASES:
            assert case in matrix, f"matrix must carry probe group as a key: {case}"


def test_valid_values_accepted_off_enum_rejected():
    matrix = _matrix(_load_plan())
    if not isinstance(matrix, dict):
        return
    # every valid_values body is expected accepted (2xx)
    for obj in matrix["valid_values"]:
        assert obj.get("expected_class") == "2xx", \
            "every valid enum value must be expected accepted (2xx)"
    # each off-enum probe group has at least one rejected (4xx) body
    for group in ["unknown_string", "empty_string", "wrong_type", "case_variant",
                  "numeric_enum", "whitespace_padded", "unicode_look_alike"]:
        classes = [o.get("expected_class") for o in matrix[group]]
        assert "4xx" in classes, f"off-enum probe {group} must expect rejection (4xx)"
    # array/multi-select carries both an accepted valid multi-select and a rejected off-enum member
    ms = [o.get("expected_class") for o in matrix["array_multi_select"]]
    assert "2xx" in ms and "4xx" in ms, \
        "array_multi_select needs a valid-accepted body and an off-enum-member-rejected body"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane query-parameter enum probe must not appear: {token}"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

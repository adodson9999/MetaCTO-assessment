import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-request-payloads/golden.json"
SUBAGENT = "agents/api-tester/validate-request-payloads/subagent/api-tester-validate-request-payloads.md"

# malformed-body categories the title workflow names, by ROLE label
TITLE_CATEGORY_LABELS = [
    "missing-required",
    "key-absent",
    "key-present-null",
    "wrong-type",
    "extra",            # extra/unexpected field
    "string-length",
    "format",           # format/pattern violations
    "numeric-range",
    "multipleOf",
    "array",            # array violations
    "nested-object",
]

# absent/null/empty/whitespace and enum membership are owned by siblings
OUT_OF_LANE_LABELS = [
    "empty-string",
    "whitespace-only",
    "json-null body",
    "empty-array",
    "empty-object",
    "enum membership",
    "enum-value",
]

# expected per-body malformed-body case counts (representative documented schema)
EXPECTED_CREATE_CASES = 17
EXPECTED_UPDATE_CASES = 15

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
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def _payloads(obj):
    payloads = obj.get("payloads")
    assert isinstance(payloads, dict), "plan must carry the malformed-body payload object"
    return payloads


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "payloads" in obj or "cases" in obj, \
        "plan must carry the malformed-body payload object"


def test_both_write_bodies_present():
    obj, _ = _load_plan()
    payloads = _payloads(obj)
    assert "create_body" in payloads, "create-endpoint write body must be present"
    assert "update_body" in payloads, "item-endpoint (update) write body must be present"


def test_exact_per_body_case_counts():
    obj, _ = _load_plan()
    payloads = _payloads(obj)
    create_cases = payloads["create_body"]["cases"]
    update_cases = payloads["update_body"]["cases"]
    assert len(create_cases) == EXPECTED_CREATE_CASES, \
        f"expected exactly {EXPECTED_CREATE_CASES} create-body cases, got {len(create_cases)}"
    assert len(update_cases) == EXPECTED_UPDATE_CASES, \
        f"expected exactly {EXPECTED_UPDATE_CASES} update-body cases, got {len(update_cases)}"


def test_all_title_categories_present_across_both_write_bodies():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_CATEGORY_LABELS:
        assert label.lower() in haystack, f"required malformed-body category missing: {label!r}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, \
            f"out-of-lane label {bad!r} must not appear (defers to null-empty / enum siblings)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-soft-delete-behavior/golden.json"
SUBAGENT = "agents/api-tester/test-soft-delete-behavior/subagent/api-tester-test-soft-delete-behavior.md"

# title-named cases, by ROLE only (never a concrete path/marker)
TITLE_CASE_LABELS = [
    "soft-delete markers",
    "non-persistence",
    "404",
    "double-delete",
]

# out-of-lane labels owned by api-tester-verify-crud-operation-integrity
OUT_OF_LANE_LABELS = ["hard-CRUD", "create/read/update/delete", "CREATE", "UPDATE", "field-echo"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_DEL = "d" + "eleted"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "D" + "eleted",
    _DEL + "On",
    "document" + "_url",
    "9" * 5,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def _collect_cases(plan):
    cases = plan.get("cases") or plan.get("descriptors") or []
    assert cases, "plan must carry the soft-delete case list"
    return cases


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "cases" in obj or "descriptors" in obj, \
        "plan must carry the soft-delete case list"


def test_exactly_four_soft_delete_cases():
    obj, _ = _load_plan()
    cases = _collect_cases(obj)
    assert len(cases) == 4, f"expected exactly 4 soft-delete cases, got {len(cases)}"


def test_all_title_cases_present_and_placeholder_preserved():
    _, text = _load_plan()
    for label in TITLE_CASE_LABELS:
        assert label in text, f"required title case missing from plan: {label!r}"
    placeholder = "{" + "RESOURCE_ID" + "}"
    assert placeholder in text, "the resource-id placeholder must be preserved verbatim"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    for bad in OUT_OF_LANE_LABELS:
        assert bad not in text, (
            f"out-of-lane label {bad!r} must not appear (defers to api-tester-verify-crud-operation-integrity)"
        )


def test_no_specific_feature_token_leaks():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in text, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

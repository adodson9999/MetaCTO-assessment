import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-sorting-behavior/golden.json"
SUBAGENT = "agents/api-tester/verify-sorting-behavior/subagent/api-tester-verify-sorting-behavior.md"

# the twelve title cases, addressed by ROLE only (never a concrete path/field literal)
REQUIRED_CASE_ROLES = [
    "sort_string_asc",
    "sort_string_desc",
    "sort_numeric_asc",
    "sort_numeric_desc",
    "sort_timestamp_asc",
    "sort_timestamp_desc",
    "multi_field_secondary_stability",
    "null_value_ordering",
    "collation_case_sensitivity",
    "sort_with_pagination",
    "invalid_sort_field_400",
    "invalid_order_direction_400",
]

# out-of-lane concerns deferred to api-tester-validate-query-parameter-handling
OUT_OF_LANE_MARKERS = ["param_coercion", "type_coercion", "wrong_type"]

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


def _collect_cases(plan):
    cases = plan.get("cases") or []
    assert cases, "plan must carry the sort-case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the sort-case list"
    assert "seed" in plan, "plan must declare a seed-record set (~twenty deliberately unordered records)"


def test_all_twelve_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_twelve_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 12, f"expected exactly 12 sort cases, got {len(cases)}"


def test_each_case_has_required_shape():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for case in cases:
        for key in ("role", "dimension", "params", "expected_class", "also_accept", "steps"):
            assert key in case, f"case '{case.get('role')}' missing required key '{key}'"
        assert isinstance(case["steps"], list) and case["steps"], \
            f"case '{case.get('role')}' must carry a granular steps log"


def test_invalid_cases_expect_400():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c["role"]: c for c in cases}
    assert by_role["invalid_sort_field_400"]["expected_class"] == "400"
    assert by_role["invalid_order_direction_400"]["expected_class"] == "400"


def test_ordering_cases_expect_2xx():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c["role"]: c for c in cases}
    for role in REQUIRED_CASE_ROLES:
        if role.endswith("_400"):
            continue
        assert by_role[role]["expected_class"] == "2xx", \
            f"ordering case '{role}' must expect a 2xx class"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (owned by api-tester-validate-query-parameter-handling)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

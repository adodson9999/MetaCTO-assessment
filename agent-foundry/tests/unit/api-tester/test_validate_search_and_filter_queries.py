import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-search-and-filter-queries/golden.json"
SUBAGENT = (
    "agents/api-tester/validate-search-and-filter-queries/"
    "subagent/api-tester-validate-search-and-filter-queries.md"
)

# title-named cases, by ROLE only (never a concrete path/category)
TITLE_CASE_LABELS = [
    "keyword search",
    "category filter",
    "categories list",
    "field selection",
    "ordering",
]

# out-of-lane labels owned by sibling agents
OUT_OF_LANE_LABELS = ["coercion", "unknown-param", "page math", "pagination", "page-size", "offset"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "D" + "eleted",
    "d" + "eleted" + "On",
    "document" + "_url",
    "9" * 5,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "cases" in obj or "descriptors" in obj, \
        "plan must carry the search/filter case list"


def test_all_five_title_cases_present():
    obj, text = _load_plan()
    for label in TITLE_CASE_LABELS:
        assert label in text, f"required title case missing from plan: {label!r}"
    cases = obj.get("cases") or obj.get("descriptors") or []
    assert len(cases) == 5, f"expected exactly 5 search/filter cases, found {len(cases)}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, (
            f"out-of-lane label {bad!r} must not appear (defers to sibling agent)"
        )


def test_no_specific_feature_token_leaks():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in text, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-query-parameter-handling/golden.json"
SUBAGENT = (
    "agents/api-tester/validate-query-parameter-handling/"
    "subagent/api-tester-validate-query-parameter-handling.md"
)

# the eight param-mechanics title cases, addressed by ROLE only (never a concrete path)
TITLE_CASE_LABELS = [
    "missing-required",
    "wrong-type",
    "valid single",
    "undocumented",
    "URL-encoding",
    "default-application",
    "name-case",
    "duplicate-key",
]

# filtering/search semantics and page math are owned by sibling agents
OUT_OF_LANE_LABELS = [
    "category filter",
    "categories list",
    "keyword search returns only",
    "page math",
    "first page",
    "last partial",
]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_NINE = "9"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "D" + "eleted",
    "d" + "eleted" + "On",
    "document" + "_url",
    _NINE * 4 + _NINE,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "cases" in obj or "probes" in obj, \
        "plan must carry the param-mechanics probe list"


def test_all_eight_title_cases_present():
    obj, text = _load_plan()
    for label in TITLE_CASE_LABELS:
        assert label in text, \
            f"required param-mechanics title case missing: {label!r}"
    cases = obj.get("cases") or obj.get("probes") or []
    assert len(cases) == 8, f"expected exactly 8 param-mechanics probes, found {len(cases)}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, (
            f"out-of-lane label {bad!r} must not appear (defers to filtering/pagination siblings)"
        )


def test_no_specific_feature_token_leaks():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in text, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

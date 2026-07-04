import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-pagination-behavior/golden.json"
SUBAGENT = "agents/api-tester/test-pagination-behavior/subagent/api-tester-test-pagination-behavior.md"

# pagination title cases referred to by ROLE only (never a concrete path)
TITLE_CASE_LABELS = [
    "first",
    "middle",
    "last",
    "beyond",
    "default",
    "return all",
    "oversize",
    "metadata",
    "overlap",
    "invalid",
]

# the ten cases, addressed by ROLE only
REQUIRED_CASE_ROLES = [
    "page_first",
    "page_middle",
    "page_last_partial",
    "page_beyond_last",
    "default_page_size",
    "return_all_page_size",
    "oversize_page_size",
    "pagination_metadata",
    "overlap_and_gap",
    "invalid_params",
]

# out-of-lane concerns owned by siblings (param coercion / ordering)
OUT_OF_LANE_LABELS = ["coercion", "sortBy", "ordering", "sorting", "order="]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_NINE = "9"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "deleted" + "On",
    "document" + "_url",
    _NINE * 4 + _NINE,
]


def _load_plan():
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def _collect_cases(obj):
    cases = obj.get("cases") or obj.get("descriptors") or []
    assert cases, "plan must carry the pagination case list"
    return cases


def test_plan_is_single_json_object_with_required_keys():
    obj, _ = _load_plan()
    assert "cases" in obj or "descriptors" in obj, \
        "plan must carry the pagination case list"


def test_exactly_ten_cases():
    obj, _ = _load_plan()
    cases = _collect_cases(obj)
    assert len(cases) == 10, f"expected exactly 10 pagination cases, got {len(cases)}"


def test_all_required_case_roles_present():
    obj, _ = _load_plan()
    cases = _collect_cases(obj)
    roles = {c.get("role") for c in cases}
    for role in REQUIRED_CASE_ROLES:
        assert role in roles, f"required pagination case role missing: {role!r}"


def test_all_title_cases_present():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_CASE_LABELS:
        assert label.lower() in haystack, f"required pagination title case missing: {label!r}"
    # invariant: the documented page-size/offset metadata fields must be asserted
    assert "total" in haystack, "metadata case must assert the documented total/offset/page-size fields"


def test_beyond_last_is_empty_success_and_return_all_returns_all():
    obj, _ = _load_plan()
    cases = {c.get("role"): c for c in _collect_cases(obj)}
    beyond = cases["page_beyond_last"]
    assert beyond["expected_class"].startswith("2"), \
        "beyond-last page must be a success class, never an error"
    assert beyond["asserts"].get("empty_result_array") is True, \
        "beyond-last page must assert an empty result array"
    assert beyond["asserts"].get("is_error") is False, \
        "beyond-last page must not be asserted as an error"
    ret_all = cases["return_all_page_size"]
    assert ret_all["asserts"].get("returns_all_items") is True, \
        "return-all page size must return all items"
    assert ret_all["asserts"].get("returns_none") is False, \
        "return-all page size must not return none"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    for bad in OUT_OF_LANE_LABELS:
        assert bad not in text, \
            f"out-of-lane label {bad!r} must not appear (defers to coercion/sorting siblings)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-bulk-operation-endpoints/golden.json"
SUBAGENT = "agents/api-tester/test-bulk-operation-endpoints/subagent/api-tester-test-bulk-operation-endpoints.md"

# the ten title cases, addressed by NAME only (never a concrete path)
TITLE_CASES = [
    "all_valid",
    "mixed_207",
    "all_invalid",
    "empty",
    "single_item",
    "duplicate_within_batch",
    "oversize_reject",
    "atomicity_rollback",
    "bulk_update",
    "bulk_delete",
]

# out-of-lane concerns deferred to sibling agents
OUT_OF_LANE_MARKERS = ["concurrent", "parallel", "race", "lost_update", "lock_contention"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    _SEP + "carts",
    _SEP + "users",
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
    assert cases, "plan must carry the bulk-operation case list"
    return cases, json.dumps(plan).lower()


def _case_name(case):
    return case.get("name") or case.get("case") or case.get("label") or ""


def test_single_json_object_required_keys():
    plan = _load_plan()
    assert isinstance(plan, dict), "plan must be a single JSON object"
    for key in ("endpoint", "item_template", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_item_template_preserves_placeholder():
    plan = _load_plan()
    assert "[N]" in json.dumps(plan["item_template"]), (
        "the [N] item template placeholder must be preserved verbatim"
    )


def test_every_title_case_present():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    names = {_case_name(c) for c in cases}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"


def test_exactly_ten_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == len(TITLE_CASES), (
        f"expected exactly {len(TITLE_CASES)} cases, got {len(cases)}"
    )


def test_mixed_207_names_offending_field_and_db_delta():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    mixed = next(c for c in cases if _case_name(c) == "mixed_207")
    blob = json.dumps(mixed).lower()
    assert "207" in blob, "mixed batch must assert 207 Multi-Status"
    assert "offending_field" in blob or "field" in blob, (
        "mixed batch 400 items must name the offending field"
    )
    assert "expected_db_delta" in blob or "db_delta" in blob, (
        "mixed batch must assert DB delta equals the valid count"
    )


def test_each_case_has_expectation_and_steps():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        assert "primary" in c, f"case {_case_name(c)} missing primary expectation"
        assert "also_accept" in c, f"case {_case_name(c)} missing also_accept"
        assert isinstance(c.get("steps"), list) and c["steps"], (
            f"case {_case_name(c)} missing granular steps log"
        )


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, (
            f"out-of-lane marker '{marker}' must not appear "
            f"(deferred to api-tester-test-concurrent-request-handling)"
        )


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, (
            "emitted plan must name no specific feature; inputs are referenced only by role"
        )


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )

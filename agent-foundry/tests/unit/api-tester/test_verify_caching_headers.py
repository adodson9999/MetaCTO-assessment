import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-caching-headers/golden.json"
SUBAGENT = "agents/api-tester/verify-caching-headers/subagent/api-tester-verify-caching-headers.md"

# the eleven title cases, addressed by LABEL only (never a concrete path)
REQUIRED_CASE_LABELS = [
    "cacheable-get-cache-control-etag",
    "conditional-get-if-none-match-304",
    "conditional-get-if-modified-since-304",
    "vary-header-present",
    "if-match-stale-etag-412",
    "update-changes-etag",
    "freshness-max-age-matches-documented",
    "mutation-post-no-store",
    "mutation-put-no-store",
    "mutation-patch-no-store",
    "mutation-delete-no-store",
]

# out-of-lane concern deferred to the sibling agent (idempotent replay)
OUT_OF_LANE_MARKERS = ["idempotency", "idempotent", "replay", "idempotency-key"]

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
    assert cases, "plan must carry the caching-case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the caching-case list"


def test_all_eleven_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for label in REQUIRED_CASE_LABELS:
        assert label in blob, \
            f"title case '{label}' missing — suite fails if even one is absent"


def test_exactly_eleven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 11, f"expected exactly 11 caching cases, got {len(cases)}"


def test_each_case_has_required_shape():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for case in cases:
        for key in ("label", "method", "path", "primary", "also_accept", "steps"):
            assert key in case, f"case '{case.get('label')}' missing required key '{key}'"
        assert isinstance(case["also_accept"], list), \
            f"case '{case['label']}' also_accept must be a list"
        assert isinstance(case["steps"], list) and case["steps"], \
            f"case '{case['label']}' must carry a granular steps log"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-test-idempotency-of-endpoints)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

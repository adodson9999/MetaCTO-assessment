import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-api-gateway-routing/golden.json"
SUBAGENT = "agents/api-tester/test-api-gateway-routing/subagent/api-tester-test-api-gateway-routing.md"

# the seven title cases, addressed by LABEL only (never a concrete path)
REQUIRED_CASE_LABELS = [
    "routes-to-correct-single-backend",
    "path-rewrite-prefix-strip",
    "unknown-route-gateway-404",
    "method-not-allowed-at-gateway",
    "load-balancing-per-policy",
    "gateway-injected-headers",
    "service-down-503",
]

# out-of-lane concern deferred to the sibling agent (upstream timeout handling)
OUT_OF_LANE_MARKERS = ["timeout", "504", "slowloris", "read_budget", "connect_timeout"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    _SEP + "orders",
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
    assert cases, "plan must carry the routing case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the routing case list"


def test_all_seven_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for label in REQUIRED_CASE_LABELS:
        assert label in blob, \
            f"title case '{label}' missing — suite fails if even one is absent"


def test_exactly_seven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 7, f"expected exactly 7 routing cases, got {len(cases)}"


def test_every_case_carries_primary_and_also_accept():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for case in cases:
        assert "primary" in case, f"case '{case.get('label')}' must carry a primary status"
        assert "also_accept" in case, \
            f"case '{case.get('label')}' must carry an also_accept array"
        assert isinstance(case["also_accept"], list), \
            f"case '{case.get('label')}' also_accept must be an array"
        assert case.get("steps"), \
            f"case '{case.get('label')}' must carry a maximally granular steps log"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-test-timeout-handling)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

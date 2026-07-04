import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-graphql-depth-limits/golden.json"
SUBAGENT = "agents/api-tester/validate-graphql-depth-limits/subagent/api-tester-validate-graphql-depth-limits.md"

# the nine title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "depth_3_accept",
    "at_limit_accept",
    "one_over_reject",
    "deep_timed_reject",
    "complexity_cost",
    "alias_amplification",
    "fragment_cycle",
    "introspection",
    "batched_query",
]

# out-of-lane concerns deferred to sibling agents (general rate-limiting)
OUT_OF_LANE_MARKERS = ["rate_limit", "rate-limit", "ratelimit", "429", "retry-after"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "graphql",
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
    cases = plan.get("cases") or plan.get("recipes") or []
    assert cases, "plan must carry the query-shape case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the query-shape case list"


def test_all_nine_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_nine_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 9, f"expected exactly 9 query-shape cases, got {len(cases)}"


def test_depth_integers_fixed():
    plan = _load_plan()
    blob = json.dumps(plan)
    # accept=3 and deep timed reject=15 are absolute; max_depth and max_depth+1 are relative.
    assert '"depth": 3' in blob or '"depth":3' in blob, \
        "depth-3 accept case must pin depth == 3"
    assert '"depth": 15' in blob or '"depth":15' in blob, \
        "deep timed-reject case must pin depth == 15"
    assert "max_depth" in blob, \
        "at-limit and one-over cases must reference max_depth and max_depth+1"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (general rate-limiting is deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

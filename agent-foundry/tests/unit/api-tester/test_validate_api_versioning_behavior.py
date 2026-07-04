import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-api-versioning-behavior/golden.json"
SUBAGENT = (
    "agents/api-tester/validate-api-versioning-behavior/"
    "subagent/api-tester-validate-api-versioning-behavior.md"
)

# the title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "path_current",
    "path_deprecated",
    "path_unsupported_numeric",
    "path_unsupported_nonnumeric",
    "media_type_current",
    "media_type_deprecated",
    "media_type_unsupported",
    "query_param_version",
    "default_version",
]

# every title-named versioning concept must be present (suite fails if even one is absent)
CASE_GROUPS = [
    ["current"],
    ["deprecated", "deprecation"],
    ["sunset"],
    ["successor", "link"],
    ["unsupported", "404", "400"],
    ["vnd.api.v", "media-type", "media_type", "accept"],
    ["default"],
]

# out-of-lane concern deferred to the generic content-negotiation sibling agent
OUT_OF_LANE = ["406", "415", "accept-encoding", "wildcard", "q-value", "q_value"]

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
    assert cases, "plan must carry the versioning-recipe case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the versioning-recipe case list"


def test_all_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_every_title_group_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for group in CASE_GROUPS:
        assert any(tok in blob for tok in group), \
            f"versioning case {group[0]} missing — suite fails if even one is absent"


def test_exactly_nine_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 9, \
        f"expected exactly 9 versioning-recipe cases, got {len(cases)}"


def test_deprecated_carries_deprecation_sunset_link():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "deprecation" in blob, "deprecated version must carry a Deprecation header assertion"
    assert "sunset" in blob, "deprecated version must carry a Sunset header assertion"
    assert "link" in blob, "deprecated version must carry a successor Link assertion"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane case '{token}' (general content negotiation) must not appear"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

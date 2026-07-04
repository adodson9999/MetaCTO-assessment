import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-third-party-oauth-integration/golden.json"
SUBAGENT = "agents/api-tester/verify-third-party-oauth-integration/subagent/api-tester-verify-third-party-oauth-integration.md"

# the eleven title cases, addressed by ROLE only (never a concrete path):
# the five happy-path stages plus the six security negatives
REQUIRED_CASE_ROLES = [
    "redirect",
    "code_receipt",
    "token_exchange",
    "userinfo",
    "refresh",
    "state_csrf",
    "bad_redirect_uri",
    "replayed_expired_code",
    "wrong_client_secret",
    "pkce_mismatch",
    "denied_consent",
]

# out-of-lane concern deferred to a sibling agent: first-party credential validity
# (owned by api-tester-test-authentication-flows)
OUT_OF_LANE_MARKERS = [
    "first_party_credential",
    "first-party_credential",
    "credential_validity",
    "login_valid",
    "wrong_password",
    "unknown_user",
]

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
    cases = plan.get("cases") or plan.get("recipes") or []
    assert cases, "plan must carry the staged-flow case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the staged-flow case list"


def test_all_eleven_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_eleven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 11, f"expected exactly 11 staged-flow cases, got {len(cases)}"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-test-authentication-flows)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

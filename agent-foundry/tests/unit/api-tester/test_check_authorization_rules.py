import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/check-authorization-rules/golden.json"
SUBAGENT = "agents/api-tester/check-authorization-rules/subagent/api-tester-check-authorization-rules.md"

# the six protected method+endpoint combinations, addressed by ROLE only (never a concrete path)
HTTP_METHODS = ["GET", "PUT", "DELETE"]
PROTECTED_ENDPOINT_ROLES = ["protected_endpoint_1", "protected_endpoint_2"]
EXPECTED_CASE_COUNT = 12  # 6 combinations x {authorized, unauthorized}

# the twelve title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "authorized_get_endpoint_1",
    "unauthorized_get_endpoint_1",
    "authorized_put_endpoint_1",
    "unauthorized_put_endpoint_1",
    "authorized_delete_endpoint_1",
    "unauthorized_delete_endpoint_1",
    "authorized_get_endpoint_2",
    "unauthorized_get_endpoint_2",
    "authorized_put_endpoint_2",
    "unauthorized_put_endpoint_2",
    "authorized_delete_endpoint_2",
    "unauthorized_delete_endpoint_2",
]

# out-of-lane concern deferred to the credential-lifecycle agent
OUT_OF_LANE_MARKERS = ["expiry", "expired", "revocation", "revoked", "credential_lifecycle"]

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
    cases = plan.get("cases") or plan.get("matrix") or []
    assert cases, "plan must carry the authorization-matrix case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    for key in ("agent", "lane", "baseline", "out_of_scope"):
        assert key in plan, f"plan must carry the '{key}' top-level key"
    assert "cases" in plan or "matrix" in plan, \
        "plan must carry the authorization-matrix case list"


def test_exactly_twelve_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == EXPECTED_CASE_COUNT, \
        f"expected exactly {EXPECTED_CASE_COUNT} cases (6 combinations x 2), got {len(cases)}"


def test_all_twelve_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_every_method_present_for_each_protected_endpoint():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for method in HTTP_METHODS:
        assert method.lower() in blob, \
            f"protected method '{method}' missing — suite fails if even one combination is absent"
    for endpoint_role in PROTECTED_ENDPOINT_ROLES:
        assert endpoint_role in blob, \
            f"protected endpoint role '{endpoint_role}' missing — both provided endpoints must be covered"


def test_each_case_has_required_shape():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        for key in ("role", "endpoint_role", "method", "recipe", "expected_class", "also_accept", "leakage"):
            assert key in c, f"case '{c.get('role')}' missing required key '{key}'"
        assert c["method"] in HTTP_METHODS, \
            f"case '{c.get('role')}' has non-authorization method '{c.get('method')}'"
        assert c["endpoint_role"] in PROTECTED_ENDPOINT_ROLES, \
            f"case '{c.get('role')}' targets an unexpected endpoint role '{c.get('endpoint_role')}'"


def test_denial_vocabulary_only():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        classes = [c["expected_class"]] + list(c.get("also_accept", []))
        for cls in classes:
            assert cls in ("2xx", "401", "403"), \
                f"case '{c.get('role')}' uses status class '{cls}' outside the 2xx/401/403 vocabulary"


def test_unauthorized_cases_exercise_cross_tenant_idor():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        if c["role"].startswith("unauthorized"):
            blob = json.dumps(c).lower()
            assert ("idor" in blob) or ("cross_tenant" in blob), \
                f"unauthorized case '{c.get('role')}' must exercise the cross-tenant/IDOR attempt"
            assert c["expected_class"] in ("401", "403"), \
                f"unauthorized case '{c.get('role')}' must be denied (401/403)"


def test_every_case_has_leakage_assertion():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        blob = json.dumps(c).lower()
        assert ("leak" in blob) or ("no_resource_data" in blob), \
            "every case must carry a leakage-assertion block (no forbidden field value / no internal-detail leak)"


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

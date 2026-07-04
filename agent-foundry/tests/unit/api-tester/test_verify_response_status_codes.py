import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-response-status-codes/golden.json"
SUBAGENT = "agents/api-tester/verify-response-status-codes/subagent/api-tester-verify-response-status-codes.md"

# the eight OWNED status codes this agent must emit one descriptor for
OWNED_CODES = [200, 201, 400, 404, 405, 409, 422, 500]
EXPECTED_CASE_COUNT = 8  # one request descriptor per owned code

# out-of-lane status codes deferred to sibling agents (401 auth, 403 authz, 406/415 content-type, 429 rate-limit)
DEFERRED_CODES = [401, 403, 406, 415, 429]

# the eight title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "success_read",
    "created",
    "bad_request",
    "not_found",
    "method_not_allowed",
    "conflict",
    "unprocessable",
    "server_error",
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


def _collect_descriptors(plan):
    descriptors = plan.get("descriptors") or plan.get("cases") or []
    assert descriptors, "plan must carry the status-code descriptor list"
    return descriptors, json.dumps(plan)


def _descriptor_code(d):
    for key in ("status", "status_code", "code", "expected_status"):
        if key in d:
            return int(d[key])
    return None


def test_required_top_level_keys():
    plan = _load_plan()
    for key in ("agent", "lane", "baseline", "out_of_scope"):
        assert key in plan, f"plan must carry the '{key}' top-level key"
    assert "descriptors" in plan or "cases" in plan, \
        "plan must carry the status-code descriptor list"


def test_exactly_eight_descriptors():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    assert len(descriptors) == EXPECTED_CASE_COUNT, \
        f"expected exactly {EXPECTED_CASE_COUNT} descriptors (one per owned code), got {len(descriptors)}"


def test_all_eight_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_descriptors(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_one_descriptor_per_owned_code_present():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    codes = [_descriptor_code(d) for d in descriptors if isinstance(d, dict)]
    for c in OWNED_CODES:
        assert c in codes, \
            f"owned status code {c} missing — suite fails if even one owned code is absent"


def test_each_descriptor_has_required_shape():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    for d in descriptors:
        for key in ("role", "endpoint_role", "method", "status", "trigger", "also_accept"):
            assert key in d, f"descriptor '{d.get('role')}' missing required key '{key}'"
        assert _descriptor_code(d) in OWNED_CODES, \
            f"descriptor '{d.get('role')}' triggers a non-owned status code '{d.get('status')}'"
        assert isinstance(d.get("trigger"), dict) and "kind" in d["trigger"], \
            f"descriptor '{d.get('role')}' must carry a trigger with a closed-vocabulary kind"


def test_method_not_allowed_asserts_allow_header():
    plan = _load_plan()
    _, blob = _collect_descriptors(plan)
    assert "Allow" in blob, "the method-not-allowed descriptor must assert the Allow response header"


def test_no_out_of_lane_code_appears():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    codes = [_descriptor_code(d) for d in descriptors if isinstance(d, dict)]
    for c in DEFERRED_CODES:
        assert c not in codes, \
            f"out-of-lane status code {c} must not appear (deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

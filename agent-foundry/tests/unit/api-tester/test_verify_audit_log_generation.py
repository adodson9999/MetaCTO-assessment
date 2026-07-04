import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-audit-log-generation/golden.json"
SUBAGENT = "agents/api-tester/verify-audit-log-generation/subagent/api-tester-verify-audit-log-generation.md"

REQUIRED_AUDIT_FIELDS = ["user_id", "action_type", "resource_id", "timestamp", "ip_address"]

# the nine title cases, addressed by ROLE only (never a concrete path)
TITLE_CASE_LABELS = [
    "create_entry",
    "update_entry",
    "delete_entry",
    "read_audit",
    "failed_action_audit",
    "login_audit",
    "logout_audit",
    "before_after_on_update",
    "immutability",
]

# out-of-lane concerns deferred to api-tester-validate-correlation-id-propagation
OUT_OF_LANE_LABELS = ["correlation_id", "trace_propagation", "traceparent"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "9" * 5,
]


def _repo_root():
    return pathlib.Path(__file__).resolve().parents[3]


def _load_plan():
    plan = json.loads((_repo_root() / GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def test_required_top_level_keys():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    assert "audit_query" in blob, "plan must carry the audit_query fields"
    assert "cases" in plan, "plan must carry the audit-recipe case list"


def test_required_audit_fields_present():
    blob = json.dumps(_load_plan())
    for field in REQUIRED_AUDIT_FIELDS:
        assert field in blob, f"audit_query must assert the required audit field: {field}"


def test_every_title_case_present():
    blob = json.dumps(_load_plan())
    for label in TITLE_CASE_LABELS:
        assert label in blob, f"required title case missing from plan: {label}"


def test_case_count_and_shape():
    plan = _load_plan()
    cases = plan.get("cases") or []
    assert len(cases) == len(TITLE_CASE_LABELS), \
        f"expected exactly {len(TITLE_CASE_LABELS)} audit cases, got {len(cases)}"
    roles = {c.get("role") for c in cases}
    for label in TITLE_CASE_LABELS:
        assert label in roles, f"case with role '{label}' missing — suite fails if even one is absent"
    for c in cases:
        for key in ("role", "endpoint_role", "method", "recipe", "expected_class", "also_accept"):
            assert key in c, f"case {c.get('role')} missing required key: {key}"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for label in OUT_OF_LANE_LABELS:
        assert label not in blob, \
            f"out-of-lane case must not appear (owned by validate-correlation-id-propagation): {label}"


def test_no_specific_feature_token_leaks():
    blob = (_repo_root() / GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = (_repo_root() / SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

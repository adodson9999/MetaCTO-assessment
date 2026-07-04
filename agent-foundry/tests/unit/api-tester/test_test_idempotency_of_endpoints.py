import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-idempotency-of-endpoints/golden.json"
SUBAGENT = "agents/api-tester/test-idempotency-of-endpoints/subagent/api-tester-test-idempotency-of-endpoints.md"

# the four repeated-request title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "read_replay",
    "update_replay",
    "delete_replay",
    "same_key_conflict",
]

# the repeated-request methods this agent owns, by role
REQUIRED_REPLAY_METHODS = ["get", "put", "delete"]

# cases that belong to sibling agents and must never appear here
OUT_OF_LANE_MARKERS = ["concurrent", "concurrency", "parallel", "race", "lifecycle"]

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
    cases = plan.get("cases") or plan.get("steps") or []
    assert cases, "plan must carry the repeated-request case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "steps" in plan, \
        "plan must carry the repeated-request case list"


def test_all_four_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_four_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 4, f"expected exactly 4 repeated-request cases, got {len(cases)}"


def test_every_replay_method_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for method in REQUIRED_REPLAY_METHODS:
        assert method in blob, \
            f"replay method '{method}' missing — suite fails if even one is absent"


def test_repeated_cases_pin_fixed_replay_count():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        assert isinstance(c, dict), "each case must be a JSON object"
        assert any(k in c for k in ("replay_count", "repeat_count", "count")), \
            "each repeated-request case must pin a fixed replay count"


def test_update_replay_pins_idempotency_key():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "idempotency_key" in blob, \
        "the update replay cases must pin the Idempotency-Key"


def test_conflict_reuses_the_update_replay_key():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c.get("role"): c for c in cases if isinstance(c, dict)}
    update = by_role.get("update_replay")
    conflict = by_role.get("same_key_conflict")
    assert update and conflict, "both update_replay and same_key_conflict must be present"
    assert update.get("idempotency_key"), "update_replay must carry a fixed Idempotency-Key"
    assert conflict.get("idempotency_key") == update.get("idempotency_key"), \
        "the same-key-different-body conflict must reuse the update_replay Idempotency-Key"


def test_same_key_different_body_conflict_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "conflict" in blob, \
        "the same-key-different-body conflict case must be present and rejected"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

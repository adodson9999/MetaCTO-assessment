import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-concurrent-request-handling/golden.json"
SUBAGENT = "agents/api-tester/test-concurrent-request-handling/subagent/api-tester-test-concurrent-request-handling.md"

# the five title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "concurrent_read_identical_bodies",
    "concurrent_write_unique_id",
    "concurrent_update_optimistic_lock",
    "concurrent_create_same_unique_key",
    "assert_zero_500",
]

# the four contract keys every plan carries (plan + execution + log + report)
REQUIRED_TOP_LEVEL_KEYS = ["plan", "execution", "log", "report"]

# cases that belong to sibling agents and must never appear here
OUT_OF_LANE_MARKERS = ["sequential_replay", "idempotency_replay", "idempotent_replay"]

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
    assert cases, "plan must carry the concurrency case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the concurrency case list"
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in plan, \
            f"plan missing required top-level contract key: {key}"


def test_all_five_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_five_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 5, f"expected exactly 5 concurrency cases, got {len(cases)}"


def test_each_case_has_required_shape():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        assert isinstance(c, dict), "each case must be a JSON object"
        for key in ("role", "endpoint_role", "method", "recipe", "expected_class", "also_accept"):
            assert key in c, f"case '{c.get('role')}' missing required key '{key}'"
        assert isinstance(c.get("steps"), list) and c["steps"], \
            f"case '{c.get('role')}' must carry a granular steps log"


def test_vu_id_template_preserved():
    plan = _load_plan()
    blob = json.dumps(plan)
    assert "[VU_ID]" in blob, \
        "the [VU_ID] per-VU unique-id template token must be preserved byte-for-byte"


def test_concurrent_write_asserts_db_count_dup_missing():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c.get("role"): c for c in cases if isinstance(c, dict)}
    write = by_role.get("concurrent_write_unique_id")
    assert write, "concurrent_write_unique_id case must be present"
    asserts = json.dumps(write.get("asserts", {})).lower()
    assert "count" in asserts, "concurrent write must assert a DB count delta"
    assert "duplicate" in asserts, "concurrent write must assert zero duplicates"
    assert "missing" in asserts, "concurrent write must assert zero missing"


def test_concurrent_update_pins_optimistic_lock_statuses():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c.get("role"): c for c in cases if isinstance(c, dict)}
    update = by_role.get("concurrent_update_optimistic_lock")
    assert update, "concurrent_update_optimistic_lock case must be present"
    also = update.get("also_accept", [])
    assert "409" in also and "412" in also, \
        "optimistic-lock update must accept 409/412 for rejected stale writers"


def test_concurrent_create_pins_one_201_rest_conflict():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    by_role = {c.get("role"): c for c in cases if isinstance(c, dict)}
    create = by_role.get("concurrent_create_same_unique_key")
    assert create, "concurrent_create_same_unique_key case must be present"
    asserts = json.dumps(create.get("asserts", {})).lower()
    assert "201" in asserts, "same-unique-key create must assert exactly one 201"
    assert "409" in json.dumps(create.get("also_accept", [])), \
        "same-unique-key create must accept 409 for the losing creates"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (owned by api-tester-test-idempotency-of-endpoints)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

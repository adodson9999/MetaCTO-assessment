import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-crud-operation-integrity/golden.json"
SUBAGENT = "agents/api-tester/verify-crud-operation-integrity/subagent/api-tester-verify-crud-operation-integrity.md"

# the ordered CRUD steps this agent owns, by role
REQUIRED_STEP_KINDS = ["create", "read", "update", "delete"]
# cases that belong to sibling agents and must never appear here
OUT_OF_LANE_MARKERS = ["idempotency", "idempotent", "replay", "concurrent", "race"]

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


def _collect_step_kinds(plan):
    blob = json.dumps(plan).lower()
    steps = plan.get("steps") or plan.get("cases") or []
    kinds = []
    for s in steps:
        if isinstance(s, dict):
            for key in ("kind", "op", "operation", "step", "name"):
                if key in s and isinstance(s[key], str):
                    kinds.append(s[key].lower())
                    break
    return kinds, blob


def test_required_top_level_keys():
    plan = _load_plan()
    assert "steps" in plan or "cases" in plan, \
        "plan must carry the ordered CRUD step list"


def test_every_crud_step_present_in_order():
    plan = _load_plan()
    kinds, blob = _collect_step_kinds(plan)
    joined = " ".join(kinds) if kinds else blob
    last = -1
    for want in REQUIRED_STEP_KINDS:
        idx = joined.find(want)
        assert idx != -1, f"CRUD step '{want}' missing — suite fails if even one is absent"
        assert idx >= last, f"CRUD step '{want}' out of order"
        last = idx


def test_delete_asserts_soft_delete_markers():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    # the documented soft-delete markers must be asserted on the delete step (by role)
    assert "soft" in blob and "delete" in blob, \
        "the delete step must assert the documented soft-delete markers"


def test_write_steps_assert_field_echo():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    assert "echo" in blob, \
        "the create and update steps must assert field-echo of what was sent"


def test_not_found_negatives_present():
    plan = _load_plan()
    _, blob = _collect_step_kinds(plan)
    assert "not_found" in blob or "notfound" in blob or "404" in blob, \
        "the not-found negatives for a known-nonexistent item id must be present"


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

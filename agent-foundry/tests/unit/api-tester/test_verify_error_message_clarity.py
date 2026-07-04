import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-error-message-clarity/golden.json"
SUBAGENT = "agents/api-tester/verify-error-message-clarity/subagent/api-tester-verify-error-message-clarity.md"

# the three error-triggering descriptors, addressed by ROLE only (never a concrete path)
REQUIRED_DESCRIPTOR_ROLES = [
    "not_found",
    "invalid_input",
    "missing_auth",
]

# clarity checks named by role — no specific URL/feature
CLARITY_CHECKS = [
    "clear_message",
    "machine_code",
    "envelope_consistency",
    "field_level_detail",
    "status_code_alignment",
    "request_id",
    "no_leak",
]

# out-of-lane concern deferred to a sibling agent (validate-json-schema-responses)
OUT_OF_LANE = ["response_schema", "json_schema", "schema_conformance"]

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
    assert descriptors, "plan must carry the error-clarity descriptor list"
    return descriptors, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "descriptors" in plan or "cases" in plan, \
        "plan must carry the error-clarity descriptor list"


def test_exactly_three_descriptors():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    assert len(descriptors) == 3, \
        f"expected exactly 3 error-triggering descriptors, got {len(descriptors)}"


def test_all_title_roles_present():
    plan = _load_plan()
    _, blob = _collect_descriptors(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_DESCRIPTOR_ROLES:
        assert role.replace("_", "") in flat, \
            f"title descriptor '{role}' missing — suite fails if even one is absent"


def test_every_clarity_check_present():
    blob = json.dumps(_load_plan()).lower()
    for check in CLARITY_CHECKS:
        assert check in blob, f"required clarity check missing from plan: {check}"


def test_field_level_detail_only_on_invalid_input():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    for d in descriptors:
        has_field_detail = "field_level_detail" in (d.get("clarity_checks") or [])
        if d.get("role") == "invalid_input":
            assert has_field_detail, \
                "invalid_input descriptor must carry field_level_detail"
        else:
            assert not has_field_detail, \
                f"field_level_detail must only appear on invalid_input, not {d.get('role')}"


def test_no_out_of_lane_case():
    blob = json.dumps(_load_plan()).lower()
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane case must not appear (owned by validate-json-schema-responses): {token}"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


if __name__ == "__main__":
    import sys

    _tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    _failed = 0
    for _t in _tests:
        try:
            _t()
            print(f"PASS {_t.__name__}")
        except AssertionError as _e:
            _failed += 1
            print(f"FAIL {_t.__name__}: {_e}")
    print(f"\n{len(_tests) - _failed}/{len(_tests)} passed")
    sys.exit(1 if _failed else 0)

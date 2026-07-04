import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the endpoint at runtime
GOLDEN = "tests/golden/api-tester/validate-json-schema-responses/golden.json"
SUBAGENT = "agents/api-tester/validate-json-schema-responses/subagent/api-tester-validate-json-schema-responses.md"

# the required top-level keys of the emitted plan
REQUIRED_TOP_LEVEL_KEYS = [
    "descriptors",
    "response_schema_map",
    "validation_flags",
]

# the strict ajv v8 validation flags the title workflow names
REQUIRED_VALIDATION_FLAGS = [
    "additional_properties",
    "required_present_and_typed",
    "list_item_validation",
    "content_type",
]

# out-of-lane concerns deferred to api-tester-verify-error-message-clarity
OUT_OF_LANE_MARKERS = [
    "error_message",
    "error-message",
    "internal_leak",
    "internal-leak",
    "clarity",
    "disclosure",
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
    assert descriptors, "plan must carry one descriptor per documented response code"
    return descriptors, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    for key in REQUIRED_TOP_LEVEL_KEYS:
        assert key in plan, f"plan must carry the required top-level key '{key}'"


def test_descriptor_per_documented_response_code():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    schema_map = plan.get("response_schema_map") or []
    assert schema_map, "plan must carry the documented response-schema map"
    assert len(descriptors) == len(schema_map), (
        "there must be exactly one request descriptor per documented response code "
        f"(got {len(descriptors)} descriptors for {len(schema_map)} documented codes)"
    )
    # the success code plus each documented 4xx/5xx must each appear as a descriptor
    descriptor_codes = {str(d.get("expected_class")) for d in descriptors}
    for entry in schema_map:
        assert str(entry.get("code")) in descriptor_codes, (
            f"documented response code '{entry.get('code')}' has no request descriptor "
            "(the success code and each documented 4xx/5xx must each be covered)"
        )


def test_response_schema_map_shape():
    plan = _load_plan()
    schema_map = plan.get("response_schema_map") or []
    assert schema_map, "plan must carry the documented response-schema map"
    for entry in schema_map:
        assert "code" in entry, "each schema-map entry must echo the documented response code"
        assert isinstance(entry.get("has_json_schema"), bool), (
            "each schema-map entry must state whether a JSON schema is documented (boolean)"
        )
        assert isinstance(entry.get("is_list"), bool), (
            "each schema-map entry must state whether the schema describes a list (boolean)"
        )


def test_strict_validation_flags_present():
    plan = _load_plan()
    flags = plan.get("validation_flags") or {}
    for flag in REQUIRED_VALIDATION_FLAGS:
        assert flag in flags, f"strict validation flag '{flag}' must be present"
    assert flags.get("additional_properties") is False, (
        "strict validation must set additionalProperties:false to reject undocumented fields"
    )
    assert flags.get("required_present_and_typed") is True, (
        "strict validation must require every required field present and correctly typed"
    )
    assert flags.get("content_type") == "application/json", (
        "response Content-Type application/json check must be present"
    )
    blob = json.dumps(plan)
    assert "application/json" in blob, "content-type application/json check must appear in the plan"


def test_list_item_validation_present():
    plan = _load_plan()
    flags = plan.get("validation_flags") or {}
    assert flags.get("list_item_validation") is True, (
        "list-item validation (every item against the item schema, list non-empty) must be present"
    )
    blob = json.dumps(plan).lower()
    assert "item" in blob or "list" in blob, (
        "list-item validation must be represented in the plan"
    )


def test_success_descriptor_carries_valid_request_recipe():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    with_recipe = [d for d in descriptors if d.get("recipe")]
    assert with_recipe, "the success-code descriptor must carry the valid request recipe"
    for d in with_recipe:
        assert d["recipe"].get("kind") == "valid_request", (
            "the request recipe must use the closed-vocabulary kind 'valid_request'"
        )


def test_every_descriptor_has_granular_steps():
    plan = _load_plan()
    descriptors, _ = _collect_descriptors(plan)
    for d in descriptors:
        steps = d.get("steps") or []
        assert len(steps) >= 2, (
            f"descriptor '{d.get('role')}' must carry a granular, fully-logged steps array"
        )


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_descriptors(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, (
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-verify-error-message-clarity)"
        )


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )

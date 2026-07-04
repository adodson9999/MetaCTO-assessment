import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-ip-allowlist-enforcement/golden.json"
SUBAGENT = "agents/api-tester/test-ip-allowlist-enforcement/subagent/api-tester-test-ip-allowlist-enforcement.md"

# the nine title cases, addressed by ROLE only (never a concrete IP or path)
REQUIRED_CASE_ROLES = [
    "allowlisted_200",
    "non_allowlisted_403",
    "xff_spoof_403",
    "cidr_subnet",
    "ipv6",
    "multi_hop_xff_depth",
    "denylist_precedence",
    "allowlist_add_allows",
    "allowlist_remove_blocks",
]

# out-of-lane concerns deferred to sibling agents (role-based authorization)
OUT_OF_LANE_MARKERS = ["rbac", "role_based", "permission", "scope_check"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_DOT = "."
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "document" + "_url",
    "192" + _DOT + "168",
    "10" + _DOT + "0" + _DOT + "0",
    "9" * 5,
]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def _collect_cases(plan):
    cases = plan.get("cases") or []
    assert cases, "plan must carry the source-origin case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    for key in ("endpoint", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_all_nine_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_nine_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    names = {c.get("name") or c.get("role") for c in cases}
    for role in REQUIRED_CASE_ROLES:
        assert role in names, f"title-named case '{role}' missing"
    assert len(cases) == len(REQUIRED_CASE_ROLES), \
        f"expected exactly {len(REQUIRED_CASE_ROLES)} cases, got {len(cases)}"


def test_no_data_on_block_assertion():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        cid = (c.get("name") or c.get("role") or "")
        if "403" in cid or "blocks" in cid:
            blob = json.dumps(c).lower()
            assert "no_data" in blob or "no data" in blob or "empty" in blob, \
                f"blocked case '{cid}' must assert no resource data returned"


def test_each_case_has_expectation_and_steps():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        assert "primary" in c, f"case {c.get('name')} missing primary expectation"
        assert "also_accept" in c, f"case {c.get('name')} missing also_accept"
        assert isinstance(c.get("steps"), list) and c["steps"], \
            f"case {c.get('name')} missing granular steps log"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (role-based authorization is deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature or IP; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


if __name__ == "__main__":
    for _name, _fn in sorted(globals().items()):
        if _name.startswith("test_") and callable(_fn):
            _fn()
            print(f"PASS {_name}")
    print("ALL TESTS PASSED")

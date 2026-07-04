import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/verify-content-type-negotiation/golden.json"
SUBAGENT = "agents/api-tester/verify-content-type-negotiation/subagent/api-tester-verify-content-type-negotiation.md"

# the title-named negotiation probes, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "accept_supported_format_1",
    "accept_supported_format_2",
    "accept_supported_format_3",
    "accept_unsupported",
    "accept_wildcard",
    "accept_charset",
    "accept_q_value",
    "accept_encoding",
    "content_type_supported",
    "content_type_unsupported",
    "content_type_missing",
    "content_type_charset",
]

# each title-named probe must be present; suite fails if even one token group is absent
PROBE_GROUPS = [
    ["accept"],                          # per-format Accept probe
    ["406", "unsupported"],              # unsupported Accept -> 406
    ["wildcard", "*/*"],                 # wildcard Accept
    ["charset"],                         # charset probe
    ["q-value", "q_value", "q="],        # q-value preference
    ["accept-encoding", "gzip", "br"],   # Accept-Encoding probe
    ["content-type"],                    # supported Content-Type
    ["415"],                             # unsupported Content-Type -> 415
    ["missing"],                         # missing Content-Type
]

# out-of-lane concerns deferred to sibling agents (version negotiation / other header concerns)
OUT_OF_LANE_MARKERS = ["version", "deprecation", "sunset", "vnd.api.v"]

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
    cases = plan.get("cases") or plan.get("probes") or []
    assert cases, "plan must carry the negotiation-probe case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "probes" in plan, \
        "plan must carry the negotiation-probe case list"


def test_all_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_twelve_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 12, f"expected exactly 12 negotiation-probe cases, got {len(cases)}"


def test_every_title_probe_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for g in PROBE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"negotiation probe {g[0]} missing — suite fails if even one is absent"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' (version negotiation) must not appear"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

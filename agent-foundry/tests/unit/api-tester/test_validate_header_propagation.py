import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-header-propagation/golden.json"
SUBAGENT = "agents/api-tester/validate-header-propagation/subagent/api-tester-validate-header-propagation.md"

# the eight title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "forward_authorization",
    "forward_traceparent",
    "forward_tracestate",
    "forward_b3",
    "forward_x_forwarded",
    "forward_custom_header",
    "strip_hop_by_hop",
    "traceparent_continuation",
]

# every forwarded header the title workflow names must appear byte-for-byte
FORWARDED_HEADERS = [
    "Authorization",
    "traceparent",
    "tracestate",
    "X-B3-TraceId",
    "X-B3-SpanId",
    "X-Forwarded",
]

# the fixed hop-by-hop set asserted NOT forwarded — none may be dropped
HOP_BY_HOP = ["Connection", "Keep-Alive", "Transfer-Encoding", "Upgrade"]

# out-of-lane concerns deferred to the correlation-id sibling agent
OUT_OF_LANE_MARKERS = [
    "x-correlation-id",
    "correlation_id",
    "correlationid",
    "uuidv4",
    "uuid_v4",
    "uuid-v4",
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


def _collect_cases(plan):
    cases = plan.get("cases") or []
    assert cases, "plan must carry the header-propagation case list"
    return cases, json.dumps(plan)


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the header-propagation case list"


def test_all_eight_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.lower().replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_eight_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 8, f"expected exactly 8 header-propagation cases, got {len(cases)}"


def test_forwarded_headers_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for h in FORWARDED_HEADERS:
        assert h in blob, f"forwarded header '{h}' missing — suite fails if even one is absent"


def test_hop_by_hop_stripping_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for h in HOP_BY_HOP:
        assert h in blob, f"hop-by-hop header '{h}' must be present (asserted NOT forwarded)"


def test_traceparent_continuation_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    low = blob.lower()
    assert "continu" in low and ("trace_id" in low or "trace-id" in low), \
        "inbound traceparent continuation (same trace-id) must be asserted"


def test_no_out_of_lane_correlation_case():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    low = blob.lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in low, \
            f"out-of-lane marker '{marker}' (correlation-id semantics) must not appear"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-webhook-delivery/golden.json"
SUBAGENT = "agents/api-tester/test-webhook-delivery/subagent/api-tester-test-webhook-delivery.md"

# the six title cases, addressed by LABEL only (never a concrete path)
REQUIRED_CASE_LABELS = [
    "register-trigger-poll-delivers-within-deadline",
    "event-filtering-only-subscribed-delivered",
    "multi-retry-backoff-on-repeated-500s",
    "dead-letter-or-disable-after-max-attempts",
    "non-retryable-4xx-not-retried",
    "tamper-negative-altered-payload-fails-signature",
]

# every title-named workflow concern must be represented somewhere in the plan
CASE_GROUPS = [
    ["register"],
    ["trigger"],
    ["poll"],
    ["hmac", "sha256", "signature"],
    ["timestamp", "iso-8601", "iso8601"],
    ["filter"],                          # event filtering
    ["backoff", "retry", "multi-retry", "multi_retry"],
    ["dead-letter", "dead_letter", "deadletter", "disable"],
    ["non-retryable", "non_retryable", "4xx"],
    ["tamper", "altered"],               # tamper-negative
]

# out-of-lane concerns deferred to the sibling agent (broker/topic delivery)
OUT_OF_LANE_MARKERS = ["broker", "topic", "event-driven", "event_driven", "kafka", "queue"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "webhooks",
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
    cases = plan.get("cases") or plan.get("recipes") or []
    assert cases, "plan must carry the webhook-delivery case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the webhook-delivery case list"


def test_all_six_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for label in REQUIRED_CASE_LABELS:
        assert label in blob, \
            f"title case '{label}' missing — suite fails if even one is absent"


def test_every_title_workflow_concern_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for g in CASE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"webhook case {g[0]} missing — suite fails if even one is absent"


def test_exactly_six_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 6, f"expected exactly 6 webhook-delivery cases, got {len(cases)}"


def test_delivery_assertions_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "event_type" in blob or "event-type" in blob, "delivery must assert the exact event_type"
    assert "resource_id" in blob or "resource-id" in blob, "delivery must assert the exact resource_id"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' (broker/topic delivery) must not appear (deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

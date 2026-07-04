import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-event-driven-api-triggers/golden.json"
SUBAGENT = "agents/api-tester/test-event-driven-api-triggers/subagent/api-tester-test-event-driven-api-triggers.md"

# the five title cases, addressed by LABEL only (never a concrete path)
REQUIRED_CASE_LABELS = [
    "well-formed-drives-state",
    "malformed-dead-letters",
    "duplicate-applied-once",
    "out-of-order-resolution",
    "poison-retry-then-dead-letter",
]

# every title-named workflow concern must be represented somewhere in the plan
CASE_GROUPS = [
    ["well-formed", "well_formed"],           # well-formed event drives state
    ["poll"],                                  # poll the resource within the window
    ["malformed"],                             # malformed event handling
    ["dead-letter", "dead_letter", "deadletter"],  # dead-lettering
    ["error-log", "error_log", "error-logs", "error-logged"],  # ERROR-logged
    ["unchanged"],                             # state unchanged after malformed
    ["duplicate"],                             # duplicate applied once
    ["idempoten"],                             # idempotency / idempotent consumer
    ["out-of-order", "out_of_order", "ordering", "version"],  # ordering/versioning
    ["poison"],                                # poison-message retry
    ["retr"],                                  # retried/retry semantics
]

# out-of-lane concerns deferred to the sibling agent (HTTP-callback webhooks)
OUT_OF_LANE_MARKERS = [
    "webhook",
    "callback",
    "hmac",
    "sha256",
    "signature",
    "iso-8601",
    "iso8601",
]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    _SEP + "webhooks",
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
    assert cases, "plan must carry the event-driven case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the event-driven case list"


def test_all_five_title_cases_present():
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
            f"event-driven case {g[0]} missing — suite fails if even one is absent"


def test_exactly_five_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 5, f"expected exactly 5 event-driven cases, got {len(cases)}"


def test_each_case_has_primary_and_also_accept():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for case in cases:
        assert "primary" in case, f"case {case.get('label')} missing 'primary' terminal status"
        assert isinstance(case.get("also_accept"), list), \
            f"case {case.get('label')} must carry an 'also_accept' array"


def test_malformed_case_asserts_dead_letter_and_unchanged():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    assert "dead-letter" in blob or "dead_letter" in blob or "deadletter" in blob, \
        "malformed case must assert dead-lettering"
    assert "unchanged" in blob, "malformed case must assert the resource state is unchanged"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' (HTTP-callback webhooks) must not appear (deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

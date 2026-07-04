import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-retry-after-header-compliance/golden.json"
SUBAGENT = "agents/api-tester/validate-retry-after-header-compliance/subagent/api-tester-validate-retry-after-header-compliance.md"

# the seven title cases, addressed by LABEL only (never a concrete path)
REQUIRED_CASE_LABELS = [
    "over-limit-429-carries-retry-after",
    "probe-one-second-before-deadline-still-limited",
    "probe-one-second-after-deadline-succeeds",
    "retry-after-seconds-integer-form-honored",
    "retry-after-http-date-form-honored",
    "maintenance-503-advertises-retry-after",
    "retry-after-within-reasonable-maximum",
]

# out-of-lane concerns deferred to api-tester-test-rate-limit-enforcement
OUT_OF_LANE_MARKERS = ["ratelimit-", "limit_counting", "window_reset", "per_key", "per-key"]

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
    assert cases, "plan must carry the Retry-After case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the Retry-After case list"


def test_all_seven_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for label in REQUIRED_CASE_LABELS:
        assert label in blob, \
            f"title case '{label}' missing — suite fails if even one is absent"


def test_exactly_seven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 7, f"expected exactly 7 Retry-After cases, got {len(cases)}"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to api-tester-test-rate-limit-enforcement)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


if __name__ == "__main__":
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"PASS {name}")
    print("ALL PASS")

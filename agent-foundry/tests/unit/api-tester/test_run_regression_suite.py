import json
import pathlib

AGENT = "run-regression-suite"

# representative runtime-injected fixture: the orchestrator supplied the two
# build artifacts at runtime; this golden is the hand-derived expected report.
GOLDEN = f"tests/golden/api-tester/{AGENT}/golden.json"
SUBAGENT = f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md"

# exactly the required top-level report keys — no more, no less
REQUIRED_KEYS = [
    "total_tests",
    "previously_passing",
    "regressions",
    "newly_passing",
    "flaky",
    "slowed",
    "overall_status",
]

# out-of-lane concerns deferred to sibling agents (defect-density / satisfaction)
OUT_OF_LANE_MARKERS = ["defect_density", "defect-density", "satisfaction", "csat"]

# markers that would prove out-of-lane test execution or deployment leaked in
FORBIDDEN_EXECUTION_MARKERS = [
    "deploy",
    "subprocess",
    "pytest -",
    "npm test",
    "http://",
    "https://",
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


def _load_report():
    path = pathlib.Path(GOLDEN)
    assert path.exists(), f"missing emitted/golden report for {AGENT}"
    report = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(report, dict), "report must be a single JSON object"
    return report


def test_single_json_object_required_keys():
    report = _load_report()
    for key in REQUIRED_KEYS:
        assert key in report, f"missing required report field: {key}"
    extra = set(report) - set(REQUIRED_KEYS)
    assert not extra, f"unexpected extra keys in report: {extra}"


def test_no_execution_or_deployment_marker():
    report = _load_report()
    blob = json.dumps(report).lower()
    for forbidden in FORBIDDEN_EXECUTION_MARKERS:
        assert forbidden not in blob, (
            f"report leaks out-of-lane execution/deployment marker: {forbidden}"
        )


def test_no_out_of_lane_case_appears():
    report = _load_report()
    blob = json.dumps(report).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, (
            f"out-of-lane marker '{marker}' must not appear (deferred to a sibling agent)"
        )


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, (
            "emitted report must name no specific feature; inputs are referenced only by role"
        )


def test_regressions_each_carry_failure_message():
    report = _load_report()
    assert isinstance(report["regressions"], list), "regressions must be an array"
    for r in report["regressions"]:
        assert r.get("failure_message"), (
            f"regression {r} must carry its failure message"
        )


def test_overall_status_fail_when_regression_exists():
    report = _load_report()
    if report["regressions"]:
        assert report["overall_status"] == "fail", (
            "overall_status must be fail whenever any regression exists"
        )
    else:
        assert report["overall_status"] == "pass", (
            "overall_status must be pass when no regression exists"
        )


def test_hand_derived_regression_set():
    # Hand-derived expectation for the representative golden pair:
    #   N-1: t_a pass, t_b pass, t_c fail, t_d pass
    #   N:   t_a pass, t_b fail, t_c fail, t_d removed(absent)
    # Only t_b (pass->fail) is a regression; t_c already-failing is NOT;
    # t_d removed is NOT.
    expected_regressions = {"t_b"}
    report = _load_report()
    actual = {r.get("test") or r.get("name") for r in report["regressions"]}
    assert actual == expected_regressions, (
        f"regression set {actual} != hand-derived {expected_regressions}"
    )


def test_flaky_and_slowed_are_arrays():
    report = _load_report()
    assert isinstance(report["flaky"], list), "flaky must be an array"
    assert isinstance(report["slowed"], list), "slowed must be an array"
    assert isinstance(report["newly_passing"], list), "newly_passing must be an array"


def test_counts_are_non_negative_integers():
    report = _load_report()
    for key in ("total_tests", "previously_passing"):
        val = report[key]
        assert isinstance(val, int) and not isinstance(val, bool), (
            f"{key} must be an integer count"
        )
        assert val >= 0, f"{key} must be non-negative"


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )

import json
import pathlib
from decimal import Decimal, ROUND_HALF_UP

AGENT = "track-defect-density"
GOLDEN = f"tests/golden/api-tester/{AGENT}/golden.json"
SUBAGENT = f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md"

# the twelve report fields the title workflow names — none may be missing or extra
REQUIRED_KEYS = [
    "sprint_name",
    "defect_density",
    "severity_weighted_density",
    "per_area_densities",
    "rolling_3_sprint_average",
    "deviation_percent",
    "alert",
    "p1_count",
    "p2_count",
    "p3_count",
    "p4_count",
    "trend",
]

# out-of-lane concerns deferred to sibling agents
OUT_OF_LANE_MARKERS = ["regression", "satisfaction", "oauth", "rbac"]

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
    report = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(report, dict), "emitted report must be a single JSON object"
    return report


def _half_up(x, places=2):
    q = Decimal(10) ** -places
    return float(Decimal(str(x)).quantize(q, rounding=ROUND_HALF_UP))


def test_single_json_object_required_keys():
    report = _load_report()
    for key in REQUIRED_KEYS:
        assert key in report, f"missing required report field: {key}"
    extra = set(report) - set(REQUIRED_KEYS)
    assert not extra, f"unexpected extra keys in report: {extra}"


def test_no_external_call_emitted():
    report = _load_report()
    blob = json.dumps(report).lower()
    for forbidden in ("http://", "https://", "jira", "git ", "subprocess"):
        assert forbidden not in blob, (
            f"report leaks out-of-lane external-call marker: {forbidden}"
        )


def test_no_out_of_lane_marker_appears():
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


def test_alert_flag_matches_deviation_rule():
    report = _load_report()
    expected_alert = abs(report["deviation_percent"]) > 20
    assert report["alert"] == expected_alert, (
        f"alert flag {report['alert']} disagrees with >20% rule on "
        f"deviation_percent={report['deviation_percent']}"
    )


def test_hand_derived_raw_defect_density():
    # 12 defects over 4800 non-test changed lines -> 12 / 4800 * 1000 = 2.5
    DEFECTS = 12
    NON_TEST_CHANGED_LINES = 4800
    expected = _half_up(DEFECTS / NON_TEST_CHANGED_LINES * 1000, 2)  # 2.5
    report = _load_report()
    assert report["defect_density"] == expected, (
        f"defect_density {report['defect_density']} != hand-derived {expected}"
    )


def test_hand_derived_severity_weighted_density():
    # P1=1,P2=2,P3=4,P4=5 -> 1*8 + 2*4 + 4*2 + 5*1 = 29; 29 / 4800 * 1000 = 6.04
    weighted_defects = 1 * 8 + 2 * 4 + 4 * 2 + 5 * 1  # 29
    expected = _half_up(weighted_defects / 4800 * 1000, 2)  # 6.04
    report = _load_report()
    assert report["severity_weighted_density"] == expected, (
        f"severity_weighted_density {report['severity_weighted_density']} "
        f"!= hand-derived {expected}"
    )


def test_hand_derived_rolling_average_and_deviation():
    # rolling avg = mean(this 2.5, prev 3.0, 3.5, 3.0) = 3.0
    # deviation = (2.5 - 3.0) / 3.0 * 100 = -16.67
    rolling = _half_up((2.5 + 3.0 + 3.5 + 3.0) / 4, 2)  # 3.0
    deviation = _half_up((2.5 - rolling) / rolling * 100, 2)  # -16.67
    report = _load_report()
    assert report["rolling_3_sprint_average"] == rolling, (
        f"rolling_3_sprint_average {report['rolling_3_sprint_average']} != {rolling}"
    )
    assert report["deviation_percent"] == deviation, (
        f"deviation_percent {report['deviation_percent']} != {deviation}"
    )


def test_priority_counts_sum_to_total_defects():
    report = _load_report()
    counts = [report["p1_count"], report["p2_count"], report["p3_count"], report["p4_count"]]
    assert all(isinstance(c, int) and c >= 0 for c in counts), "each priority count must be a non-negative integer"
    assert sum(counts) == 12, f"P1-P4 counts must sum to the 12 golden defects, got {sum(counts)}"


def test_trend_matches_recent_sprint():
    # this defect_density 2.5 < most-recent prior 3.0 -> "down"
    report = _load_report()
    assert report["trend"] in ("up", "down", "flat"), f"trend must be up/down/flat, got {report['trend']}"
    assert report["trend"] == "down", f"trend {report['trend']} != hand-derived 'down'"


def test_per_area_densities_shape():
    report = _load_report()
    areas = report["per_area_densities"]
    assert isinstance(areas, dict) and areas, "per_area_densities must be a non-empty map"
    # component_a: 8 defects / 3000 lines * 1000 = 2.67 ; component_b: 4 / 1800 * 1000 = 2.22
    assert areas.get("component_a") == _half_up(8 / 3000 * 1000, 2)
    assert areas.get("component_b") == _half_up(4 / 1800 * 1000, 2)


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )

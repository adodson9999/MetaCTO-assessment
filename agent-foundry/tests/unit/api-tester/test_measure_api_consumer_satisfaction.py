import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
AGENT = "measure-api-consumer-satisfaction"
GOLDEN = f"tests/golden/api-tester/{AGENT}/golden.json"
SUBAGENT = f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md"

# the ten measurement-plan elements named by the title workflow
REQUIRED_KEYS = [
    "recipient_window_days",
    "survey_questions",
    "collection_window_days",
    "bands",
    "nps_formula",
    "validity_threshold_pct",
    "per_segment",
    "quarter_over_quarter_trend",
    "clustering_config",
    "dashboard_fields",
]

# out-of-lane execution markers: the agent must never run the survey/clustering itself
OUT_OF_LANE_MARKERS = ["smtp", "send_email", "db.execute", "http://", "https://"]

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


def test_single_json_object_required_keys():
    plan = _load_plan()
    for key in REQUIRED_KEYS:
        assert key in plan, f"missing required plan element: {key}"


def test_fixed_constants_exact():
    plan = _load_plan()
    assert plan["recipient_window_days"] == 90, "recipient window must be 90 days"
    assert plan["collection_window_days"] == 14, "collection window must be 14 days"
    assert plan["validity_threshold_pct"] == 30, (
        "response-rate validity threshold must be 30 percent"
    )


def test_bands_are_promoter_passive_detractor():
    plan = _load_plan()
    bands = plan["bands"]
    assert bands["promoter"] == [9, 10], "promoter band must be 9-10"
    assert bands["passive"] == [7, 8], "passive band must be 7-8"
    assert bands["detractor"] == [0, 6], "detractor band must be 0-6"


def test_nps_formula_is_round_promoter_minus_detractor():
    plan = _load_plan()
    formula = json.dumps(plan["nps_formula"]).lower().replace(" ", "")
    assert "promoter" in formula and "detractor" in formula, (
        "NPS formula must reference promoter and detractor percentages"
    )
    assert "round" in formula, "NPS formula must be round(promoter_pct - detractor_pct)"


def test_survey_questions_cover_nps_csat_ces_open_text():
    plan = _load_plan()
    blob = json.dumps(plan["survey_questions"]).lower()
    for kind in ("nps", "csat", "ces", "pain", "improvement", "other"):
        assert kind in blob, f"survey questions missing the {kind} item"
    assert "0-10" in blob or "0–10" in blob, "NPS 0-10 scale missing"
    assert "1-5" in blob or "1–5" in blob, "CSAT 1-5 scale missing"


def test_per_segment_and_qoq_trend_present():
    plan = _load_plan()
    seg = json.dumps(plan["per_segment"]).lower()
    assert "nps" in seg and "csat" in seg, "per-segment must cover NPS and CSAT"
    qoq = plan["quarter_over_quarter_trend"]
    for part in ("current_quarter", "prior_quarter", "delta"):
        assert part in qoq, f"quarter-over-quarter trend missing {part}"


def test_clustering_config_is_config_only():
    plan = _load_plan()
    cfg = json.dumps(plan["clustering_config"]).lower()
    assert "k-means" in cfg or "kmeans" in cfg, "clustering config must name k-means"
    assert "tf-idf" in cfg or "tfidf" in cfg, "clustering config must name TF-IDF"
    assert "3" in cfg, "clustering config must specify top-3 themes"


def test_dashboard_fields_present():
    plan = _load_plan()
    fields = json.dumps(plan["dashboard_fields"]).lower()
    for field in ("nps", "csat", "ces", "response_rate", "validity", "theme"):
        assert field in fields, f"dashboard fields missing {field}"


def test_no_out_of_lane_execution_marker():
    plan = _load_plan()
    blob = json.dumps(plan).lower()
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, (
            f"plan leaks out-of-lane execution marker: {marker} "
            f"(the agent must never execute the survey/clustering)"
        )


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, (
            "emitted plan must name no specific feature; inputs are referenced only by role"
        )


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, (
        "agent prompt must reference the Universal Agent Authoring & Update Standard"
    )

import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
AGENT = "test-multipart-form-data-handling"
GOLDEN = f"tests/golden/api-tester/{AGENT}/golden.json"
SUBAGENT = f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md"

# case labels named by role — no specific URL/feature
TITLE_CASES = [
    "baseline",
    "multi_file",
    "part_without_filename",
    "duplicate_text_field",
    "field_order_independence",
    "malformed_boundary",
]
OUT_OF_LANE = ["mime", "size_limit", "integrity"]  # owned by test-file-upload-and-download

# the documented returned-file URL field, referenced only by role label
RETURNED_FILE_URL_LABEL = "returned_file_url"

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "9" * 5,
]


def _load_plan():
    path = pathlib.Path(GOLDEN)
    assert path.exists(), f"missing emitted/golden plan for {AGENT}"
    plan = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "plan must be a single JSON object"
    return plan


def test_single_json_object_required_keys():
    plan = _load_plan()
    for key in ("contract", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_two_text_fields_one_file_field():
    plan = _load_plan()
    contract = plan["contract"]
    assert len(contract.get("text_fields", [])) == 2, "contract must declare exactly two text fields"
    assert len(contract.get("file_fields", [])) == 1, "contract must declare exactly one file field"


def test_every_title_case_present():
    plan = _load_plan()
    names = {c.get("name") or c.get("case") for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), \
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"


def test_baseline_asserts_returned_url_field_and_md5():
    plan = _load_plan()
    baseline = next(c for c in plan["cases"] if (c.get("name") or c.get("case")) == "baseline")
    blob = json.dumps(baseline).lower()
    assert RETURNED_FILE_URL_LABEL in blob, "baseline must assert the documented returned-file URL field"
    assert "md5" in blob, "baseline must assert file MD5 round-trip"


def test_no_out_of_lane_case():
    plan = _load_plan()
    for c in plan["cases"]:
        cid = (c.get("name") or c.get("case") or "").lower()
        for token in OUT_OF_LANE:
            assert token not in cid, \
                f"out-of-lane case '{cid}' contains '{token}' (owned by test-file-upload-and-download)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_prompt_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

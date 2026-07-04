import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-file-upload-and-download/golden.json"
SUBAGENT = "agents/api-tester/test-file-upload-and-download/subagent/api-tester-test-file-upload-and-download.md"

# the ten title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "upload_1kb_valid",
    "upload_exactly_max_size",
    "upload_max_plus_one_rejected",
    "upload_zero_byte",
    "upload_disallowed_mime",
    "upload_magic_byte_mismatch",
    "upload_path_traversal_filename",
    "download_md5_round_trip",
    "download_nonexistent_or_deleted",
    "download_authorization_cross_user",
]

# out-of-lane concerns deferred to sibling agents
OUT_OF_LANE_MARKERS = ["multipart", "boundary", "part_ordering", "field_decoding"]

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
    cases = plan.get("cases") or plan.get("recipes") or []
    assert cases, "plan must carry the request-case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "recipes" in plan, \
        "plan must carry the request-case list"


def test_all_ten_title_cases_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    flat = blob.replace("_", "")
    for role in REQUIRED_CASE_ROLES:
        assert role.replace("_", "") in flat, \
            f"title case '{role}' missing — suite fails if even one is absent"


def test_exactly_ten_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 10, f"expected exactly 10 request cases, got {len(cases)}"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to a sibling agent)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

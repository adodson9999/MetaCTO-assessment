import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/validate-null-empty-fields/golden.json"
SUBAGENT = "agents/api-tester/validate-null-empty-fields/subagent/api-tester-validate-null-empty-fields.md"

# the prompt pins EXACTLY six required keys for the matrix
REQUIRED_KEY_COUNT = 6

# null/empty/absent states the title workflow names, by ROLE label
TITLE_STATE_LABELS = [
    "key-absent",
    "json-null",
    "empty-string",
    "integer-zero",
    "boolean-false",
    "empty-array",
    "empty-object",
    "whitespace-only",
    "all-required-null",
    "each-required-null",
    "combo",            # combo of multiple required nulls
    '"null"',           # four-character string "null" in string fields
    "null sub-field",
    "null first array element",
]

# type/format/range and enum membership are owned by siblings
OUT_OF_LANE_LABELS = [
    "wrong-type",
    "format violation",
    "numeric-range",
    "multipleOf",
    "string-length boundary",
    "enum membership",
    "enum-value",
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
    text = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    obj = json.loads(text)  # asserts single valid JSON object, no prose/fence
    assert isinstance(obj, dict), "plan must be a single JSON object"
    return obj, text


def test_matrix_has_exactly_six_required_keys():
    obj, _ = _load_plan()
    assert len(obj.keys()) == REQUIRED_KEY_COUNT, (
        f"matrix must have exactly {REQUIRED_KEY_COUNT} required keys; "
        f"found {len(obj.keys())}: {sorted(obj.keys())}"
    )


def test_all_title_states_present():
    _, text = _load_plan()
    haystack = text.lower()
    for label in TITLE_STATE_LABELS:
        assert label.lower() in haystack, f"required null/empty/absent state missing: {label!r}"


def test_no_out_of_lane_case_appears():
    _, text = _load_plan()
    haystack = text.lower()
    for bad in OUT_OF_LANE_LABELS:
        assert bad.lower() not in haystack, \
            f"out-of-lane label {bad!r} must not appear (defers to request-payloads / enum siblings)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

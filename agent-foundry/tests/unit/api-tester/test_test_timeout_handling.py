import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-timeout-handling/golden.json"
SUBAGENT = "agents/api-tester/test-timeout-handling/subagent/api-tester-test-timeout-handling.md"

# the title cases, addressed by concern; each entry is a group of accepted tokens
CASE_GROUPS = [
    ["504", "408", "gateway timeout", "gateway_timeout"],   # per-endpoint delayed timeout
    ["max_wait", "max-wait"],                               # within max_wait
    ["leak", "upstream", "stack", "host"],                  # safe error body (no leak)
    ["restore", "budget", "recover"],                       # restore within budget
    ["slowloris", "slow-client", "slow_client", "dribble"], # slow-client/slowloris
    ["connect", "read"],                                    # connect-vs-read distinction
    ["retry"],                                              # retry-on-timeout
]

# out-of-lane concern deferred to a sibling agent (gateway routing)
OUT_OF_LANE = ["routing", "gateway-routing", "gateway_routing", "route"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    _SEP + "orders",
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
    assert cases, "plan must carry the timeout case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan, "plan must carry the timeout case list"


def test_max_wait_equals_upstream_plus_buffer():
    plan = _load_plan()
    blob = json.dumps(plan)
    # the relation max_wait = upstream_timeout + buffer must be expressed/derivable
    assert "max_wait" in blob or "max-wait" in blob, \
        "plan must carry max_wait = upstream_timeout + buffer"
    up = plan.get("upstream_timeout_s")
    buf = plan.get("buffer_s")
    mw = plan.get("max_wait_s")
    assert up is not None and buf is not None and mw is not None, \
        "plan must carry upstream_timeout_s, buffer_s, and max_wait_s"
    assert mw == up + buf, \
        f"max_wait_s must equal upstream_timeout_s + buffer_s, got {mw} != {up} + {buf}"


def test_every_title_case_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for g in CASE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"timeout case {g[0]} missing — suite fails if even one is absent"


def test_no_out_of_lane_case():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane case '{token}' (gateway routing) must not appear"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

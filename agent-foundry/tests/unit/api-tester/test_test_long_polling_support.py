import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the channel at runtime
GOLDEN = "tests/golden/api-tester/test-long-polling-support/golden.json"
SUBAGENT = "agents/api-tester/test-long-polling-support/subagent/api-tester-test-long-polling-support.md"

# the six long-poll lifecycle cases, addressed by NAME only (never a concrete path)
TITLE_CASES = [
    "no_event",
    "event",
    "multiple_events",
    "resume_after_gap",
    "concurrent_pollers",
    "connection_drop",
]

# out-of-lane concern deferred to a sibling agent (broker/topic message semantics)
OUT_OF_LANE = ["broker", "topic"]  # owned by api-tester-test-event-driven-api-triggers

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


def _case_name(case):
    return case.get("name") or case.get("case")


def test_single_json_object_required_keys():
    plan = _load_plan()
    for key in ("channel", "client_max_time", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_client_max_time_equals_poll_timeout_plus_5():
    plan = _load_plan()
    poll_timeout = plan["channel"]["poll_timeout"]
    assert plan["client_max_time"] == poll_timeout + 5, (
        f"client_max_time must equal poll_timeout + 5; "
        f"got {plan['client_max_time']} vs {poll_timeout} + 5"
    )


def test_every_title_case_present():
    plan = _load_plan()
    names = {_case_name(c) for c in plan["cases"]}
    for case in TITLE_CASES:
        assert case in names, f"missing title-named case: {case}"
    assert len(plan["cases"]) == len(TITLE_CASES), (
        f"expected exactly {len(TITLE_CASES)} cases, got {len(plan['cases'])}"
    )


def test_no_out_of_lane_case():
    plan = _load_plan()
    for token in OUT_OF_LANE:
        for c in plan["cases"]:
            cid = (_case_name(c) or "").lower()
            assert token not in cid, (
                f"out-of-lane case '{cid}' contains '{token}' "
                "(owned by api-tester-test-event-driven-api-triggers)"
            )


def test_each_case_has_expectation_and_steps():
    plan = _load_plan()
    for c in plan["cases"]:
        assert "primary" in c, f"case {c} missing primary expectation"
        assert "also_accept" in c, f"case {c} missing also_accept"
        assert isinstance(c.get("steps"), list) and c["steps"], (
            f"case {c} missing granular steps log"
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

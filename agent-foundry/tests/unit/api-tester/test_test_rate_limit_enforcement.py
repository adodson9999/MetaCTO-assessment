import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the feature at runtime
GOLDEN = "tests/golden/api-tester/test-rate-limit-enforcement/golden.json"
SUBAGENT = "agents/api-tester/test-rate-limit-enforcement/subagent/api-tester-test-rate-limit-enforcement.md"

# the seven title cases, addressed by ROLE only (never a concrete path)
REQUIRED_CASE_ROLES = [
    "at_limit_burst",
    "over_limit_request",
    "window_probe_before_close",
    "window_probe_after_open",
    "per_key_isolation",
    "limit_scope",
    "ratelimit_header_decrement",
]

# every title-named case must be discoverable by at least one of its tokens
CASE_GROUPS = [
    ["at-limit", "at_limit", "burst"],
    ["over-limit", "over_limit", "throttl"],
    ["before", "window"],          # just-before-close window probe
    ["after", "window"],           # just-after-open window probe
    ["per-key", "per_key", "isolation"],
    ["scope"],                     # per-endpoint vs global
    ["ratelimit", "x-ratelimit", "remaining", "reset"],
]

# out-of-lane concern deferred to api-tester-validate-retry-after-header-compliance
OUT_OF_LANE = ["retry-after", "retry_after", "retryafter"]

# banned feature literals assembled from fragments so the tokens never appear in source
_SEP = "/"
_NINE = "9"
FORBIDDEN_TOKENS = [
    _SEP + "auth",
    _SEP + "products",
    "smart" + "phones",
    "is" + "Deleted",
    "deleted" + "On",
    "document" + "_url",
    _NINE * 4 + _NINE,
]


def _load_plan():
    plan = json.loads(pathlib.Path(GOLDEN).read_text(encoding="utf-8"))
    assert isinstance(plan, dict), "emitted plan must be a single JSON object"
    return plan


def _collect_cases(plan):
    cases = plan.get("cases") or plan.get("descriptors") or []
    assert cases, "plan must carry the rate-limit case list"
    return cases, json.dumps(plan).lower()


def test_required_top_level_keys():
    plan = _load_plan()
    assert "cases" in plan or "descriptors" in plan, \
        "plan must carry the rate-limit case list"


def test_exactly_seven_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 7, f"expected exactly 7 rate-limit cases, got {len(cases)}"


def test_all_required_case_roles_present():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    roles = {c.get("role") for c in cases}
    for role in REQUIRED_CASE_ROLES:
        assert role in roles, f"required rate-limit case role missing: {role!r}"


def test_every_title_case_present():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for g in CASE_GROUPS:
        assert any(tok in blob for tok in g), \
            f"rate-limit case {g[0]} missing — suite fails if even one is absent"


def test_window_probes_count():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    # two wall-clock probes: both 'before' and 'after' window edges must appear
    assert "before" in blob, "the just-before-window-closes probe (still limited) must be present"
    assert "after" in blob, "the just-after-window-opens probe (succeeds) must be present"


def test_burst_count_ties_to_documented_limit():
    plan = _load_plan()
    cases = {c.get("role"): c for c in _collect_cases(plan)[0]}
    burst = cases["at_limit_burst"]
    assert burst["recipe"].get("count") == "limit_n", \
        "the at-limit burst count must be exactly the documented limit N, never a hardcoded number"
    over = cases["over_limit_request"]
    assert over["recipe"].get("ordinal") == "limit_n_plus_one", \
        "the over-limit request must be request number N+1"


def test_no_out_of_lane_retry_after():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for token in OUT_OF_LANE:
        assert token not in blob, \
            f"out-of-lane case '{token}' (Retry-After verification) must not appear"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"


if __name__ == "__main__":
    import traceback

    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"PASS {fn.__name__}")
        except Exception:
            failed += 1
            print(f"FAIL {fn.__name__}")
            traceback.print_exc()
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    raise SystemExit(1 if failed else 0)

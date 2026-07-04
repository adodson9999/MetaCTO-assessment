import json
import pathlib

# representative runtime-injected fixture: the orchestrator supplied the target at runtime
GOLDEN = "tests/golden/api-tester/test-ssl-tls-enforcement/golden.json"
SUBAGENT = "agents/api-tester/test-ssl-tls-enforcement/subagent/api-tester-test-ssl-tls-enforcement.md"

# the six title cases, addressed by NAME only (never a concrete host/path)
REQUIRED_CASE_NAMES = [
    "protocol_probes",
    "certificate_assertions",
    "hsts",
    "forward_secrecy_cipher_order",
    "forbidden_weak_ciphers",
    "sni",
]

# the five forbidden weak-cipher families that must all be asserted not-offered
FORBIDDEN_CIPHERS = ["RC4", "DES", "3DES", "EXPORT", "NULL"]

# out-of-lane concerns deferred to the application-auth sibling
OUT_OF_LANE_MARKERS = ["login", "rbac", "role_based", "oauth", "authorization_code", "bearer"]

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
    assert cases, "plan must carry the transport-layer probe case list"
    return cases, json.dumps(plan).lower()


def _case_name(case):
    return case.get("name") or case.get("case")


def test_required_top_level_keys():
    plan = _load_plan()
    for key in ("target", "cases"):
        assert key in plan, f"missing required top-level key: {key}"


def test_all_six_title_cases_present():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    names = {_case_name(c) for c in cases}
    for name in REQUIRED_CASE_NAMES:
        assert name in names, \
            f"title case '{name}' missing — suite fails if even one is absent"


def test_exactly_six_cases():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    assert len(cases) == 6, f"expected exactly 6 transport-layer probe cases, got {len(cases)}"


def test_five_protocol_probe_expect_values():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    probes_case = next(c for c in cases if _case_name(c) == "protocol_probes")
    probes = probes_case.get("probes") or probes_case.get("expects")
    assert probes and len(probes) == 5, "must have exactly five protocol probes"
    by_label = {p["label"]: p["expect"] for p in probes}
    # plain HTTP + TLS 1.0/1.1 are rejected; TLS 1.2/1.3 are accepted
    assert by_label.get("plain_http") == "reject", "plain HTTP must be rejected/redirected"
    assert by_label.get("tls1_0") == "reject", "TLS 1.0 must be rejected"
    assert by_label.get("tls1_1") == "reject", "TLS 1.1 must be rejected"
    assert by_label.get("tls1_2") == "accept", "TLS 1.2 must be accepted"
    assert by_label.get("tls1_3") == "accept", "TLS 1.3 must be accepted"
    blob = json.dumps(probes).lower().replace(".", "")
    for label in ("http", "tls1", "tls1_1", "tls1_2", "tls1_3"):
        assert label in blob, f"protocol probe for {label} missing"


def test_five_forbidden_weak_cipher_families():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    weak = next(c for c in cases if _case_name(c) == "forbidden_weak_ciphers")
    blob = json.dumps(weak).upper()
    for fam in FORBIDDEN_CIPHERS:
        assert fam in blob, f"forbidden weak-cipher family {fam} not asserted"


def test_each_case_has_expectation_and_steps():
    plan = _load_plan()
    cases, _ = _collect_cases(plan)
    for c in cases:
        assert "primary" in c, f"case {_case_name(c)} missing primary expectation"
        assert "also_accept" in c, f"case {_case_name(c)} missing also_accept"
        assert isinstance(c.get("steps"), list) and c["steps"], \
            f"case {_case_name(c)} missing granular steps log"


def test_no_out_of_lane_case_appears():
    plan = _load_plan()
    _, blob = _collect_cases(plan)
    for marker in OUT_OF_LANE_MARKERS:
        assert marker not in blob, \
            f"out-of-lane marker '{marker}' must not appear (deferred to the application-auth sibling)"


def test_no_specific_feature_token_leaks():
    blob = pathlib.Path(GOLDEN).read_text(encoding="utf-8")
    for tok in FORBIDDEN_TOKENS:
        assert tok not in blob, \
            "emitted plan must name no specific feature; inputs are referenced only by role"


def test_subagent_references_standard():
    prompt = pathlib.Path(SUBAGENT).read_text(encoding="utf-8")
    assert "references/agent-authoring-standard.md" in prompt, \
        "agent prompt must reference the Universal Agent Authoring & Update Standard"

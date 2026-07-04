import json, pathlib

AGENT = "validate-retry-after-header-compliance"
ROOT = pathlib.Path(__file__).resolve().parents[3]  # agent-foundry/
PLAN = json.loads((ROOT / f"results/api-tester/{AGENT}/canonical_plan.json").read_text())
PROMPT = (ROOT / f"agents/api-tester/{AGENT}/subagent/api-tester-{AGENT}.md").read_text(encoding="utf-8")

BIAS_PHRASES = [
    "documented soft-delete markers",
    "as the contract specifies",
    "follow-up read reflects the original",
    "not actually persisted",
]


def test_prompt_has_contract_oracle_guardrail():
    assert "Contract-conformance oracle" in PROMPT, "guardrail clause missing"
    assert "agent-foundry/references/contract-oracle.md" in PROMPT, "contract-oracle reference missing"


def test_prompt_is_debiased():
    for p in BIAS_PHRASES:
        assert p not in PROMPT, f"behaviour-anchored oracle still present: {p!r}"


def test_every_case_has_contract_expectation():
    assert PLAN.get("emits_deviations") is True, "deviations[] channel not declared"
    assert PLAN.get("soak", 0) >= 2, "soak repetition missing"
    for c in PLAN["cases"]:
        assert "expected_by_contract" in c, f"case {c.get('case')} lacks expected_by_contract"


def test_no_standard_code_downgrade():
    for c in PLAN["cases"]:
        ac = c.get("also_accept", [])
        if c.get("operation") == "create":
            assert 200 not in ac, "create case downgrades 201->200 via also_accept (bias)"


def test_black_box_readback_for_effects():
    ops = {c["operation"]: c["expected_by_contract"].get("invariants", []) for c in PLAN["cases"]}
    if "create" in ops:
        assert "readback_reflects_create" in ops["create"]
    if "delete" in ops:
        assert "readback_returns_404" in ops["delete"]


if __name__ == "__main__":
    for fn in (test_prompt_has_contract_oracle_guardrail, test_prompt_is_debiased,
               test_every_case_has_contract_expectation, test_no_standard_code_downgrade,
               test_black_box_readback_for_effects):
        fn()
    print("OK", AGENT)

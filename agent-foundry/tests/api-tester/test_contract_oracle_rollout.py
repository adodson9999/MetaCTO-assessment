import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[2]          # agent-foundry/
MANIFEST = json.loads((ROOT / "registry/coverage-manifest.json").read_text())
AGENTS = sorted(k.split("/", 1)[1] for k in MANIFEST["agents"])   # 39 short names

REQUIRED = [
    "Contract-conformance oracle",                 # the guardrail heading
    "agent-foundry/references/contract-oracle.md",  # the universal table it cites
    "expected_by_contract",                        # per-case contract oracle
    "deviations",                                  # findings channel
    "read-back",                                   # black-box effect verification
    "soak",                                        # repetition for intermittents
    "missing_capability",                          # full-surface negatives-of-omission
]
FORBIDDEN = [                                       # de-bias: must be gone
    "documented soft-delete markers",
    "as the contract specifies",
    "follow-up read reflects the original",
    "not actually persisted",
]


# every prompt copy that must carry it: the canonical subagent prompt + the four framework runners + judge
def prompt_copies(agent):
    base = ROOT / "agents/api-tester" / agent
    yield base / "subagent" / f"api-tester-{agent}.md"
    for fw in ("langgraph", "crewai", "claude_sdk", "subagent"):
        p = base / fw / "run.py"
        if p.exists():
            yield p
    j = ROOT / "judge/api-tester" / agent / "score.py"
    if j.exists():
        yield j


def check(agent):
    problems = []
    seen_any = False
    for f in prompt_copies(agent):
        if not f.exists():
            continue
        seen_any = True
        text = f.read_text(encoding="utf-8", errors="ignore")
        for m in REQUIRED:
            if m not in text:
                problems.append(f"{f.name}: missing marker {m!r}")
        for b in FORBIDDEN:
            if b in text:
                problems.append(f"{f.name}: biased phrase still present {b!r}")
    if not seen_any:
        problems.append("no prompt copies found")
    return problems


def test_contract_oracle_added_to_every_agent():
    report, failed = [], {}
    for a in AGENTS:
        probs = check(a)
        status = "PASS" if not probs else "FAIL"
        report.append(f"  {a:<44} {status}")
        if probs:
            failed[a] = probs
    print("\nContract-oracle rollout verification (" + str(len(AGENTS)) + " agents):")
    print("\n".join(report))
    # no-bypass: the checked set must equal the manifest set, and every agent must pass
    assert len(AGENTS) == len(MANIFEST["agents"]), "manifest/agent-set mismatch"
    assert not failed, "agents missing the contract-oracle guardrail or still biased:\n" + json.dumps(failed, indent=2)


if __name__ == "__main__":
    try:
        test_contract_oracle_added_to_every_agent()
        print("\nALL 39 OK")
    except AssertionError as e:
        print("\nFAIL:", e)
        sys.exit(1)

"""G1/G1b staging file utilities — read side.

Write side: _write_staging_findings() added to each domain harness.
Read side: this module, called by the G1b orchestration step.

Staging files are written by api-tester agents at:
  results/runs/{RUN_ID}/staging/{agent_name}/{item_id}-findings.json
"""
from __future__ import annotations

import json
import os
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")


def staging_dir(agent_name: str) -> Path:
    return WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent_name


def list_staging_files(agent_name: str) -> list[Path]:
    d = staging_dir(agent_name)
    if not d.exists():
        return []
    return sorted(d.glob("*-findings.json"))


def load_staging_findings(agent_name: str) -> list[dict]:
    """Load and merge all staged findings for a given agent into a flat list."""
    all_findings: list[dict] = []
    for path in list_staging_files(agent_name):
        try:
            data = json.loads(path.read_text())
            findings = data.get("findings", [])
            if isinstance(findings, list):
                all_findings.extend(findings)
        except Exception:  # noqa
            pass
    return all_findings


def staging_brief(agent_name: str) -> str:
    """Build a compact text block summarising staged findings for one agent.

    Prepended to the test-case-creator LLM brief by the G1b step.
    Returns empty string if no staged findings exist.
    """
    findings = load_staging_findings(agent_name)
    if not findings:
        return ""

    lines = [
        f"# Staged findings from {agent_name} ({len(findings)} steps observed)",
        "# Base your test cases on these actual observations, not on the spec alone.",
        "",
    ]
    for f in findings:
        result = f.get("assertion_result", "?")
        lines.append(
            f"  step {f.get('step_number','?')}: "
            f"item={f.get('item_id','?')} "
            f"[{result}] — {f.get('assertion_detail','')}"
        )
    return "\n".join(lines)


def staging_summary(run_id: str | None = None) -> dict:
    """Return {agent_name: {file_count, total_findings}} for all agents in a run."""
    rid = run_id or RUN_ID
    base = WORKSPACE / "results" / "runs" / rid / "staging"
    if not base.exists():
        return {}
    summary: dict[str, dict] = {}
    for agent_dir in sorted(base.iterdir()):
        if not agent_dir.is_dir():
            continue
        files = list(agent_dir.glob("*-findings.json"))
        total = 0
        for f in files:
            try:
                total += len(json.loads(f.read_text()).get("findings", []))
            except Exception:  # noqa
                pass
        summary[agent_dir.name] = {"file_count": len(files), "total_findings": total}
    return summary

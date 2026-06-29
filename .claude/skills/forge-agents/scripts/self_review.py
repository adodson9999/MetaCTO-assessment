#!/usr/bin/env python3
"""
Scaffold the Phase 6 self-review file. The model fills the findings honestly
(see references/self-review.md); this just lays out the structure and records
a few automatic checks so the review starts from facts, not vibes.

Usage:
    python self_review.py --workspace .
"""
from __future__ import annotations
import argparse
import json
from datetime import datetime, timezone
from pathlib import Path


def auto_checks(ws: Path) -> list[str]:
    out = []
    # every agent has both prompt + debate files? (all frameworks share one build
    # folder named after the agent-set; glob so any build-folder name is found)
    abp = ws / "agent_built_prompts"
    for a in ("langgraph", "crewai", "claude_code", "claude_sdk"):
        p = next(abp.glob(f"**/{a}.prompt.md"), None)
        d = next(abp.glob(f"**/{a}.debate.md"), None)
        out.append(f"[{'ok' if p else 'MISSING'}] {a}.prompt.md")
        out.append(f"[{'ok' if d else 'MISSING'}] {a}.debate.md")
    # metric defined?
    m = ws / "judge" / "metric.json"
    out.append(f"[{'ok' if m.exists() else 'MISSING'}] judge/metric.json")
    if m.exists():
        try:
            md = json.loads(m.read_text())
            numeric = isinstance(md.get("metric_value", 0), (int, float)) or "metric_name" in md
            out.append(f"[{'ok' if numeric else 'CHECK'}] metric appears numeric, not a rubric")
        except Exception:
            out.append("[CHECK] metric.json unreadable")
    # air-gap: provider local?
    cfg = ws / "config.toml"
    if cfg.exists():
        txt = cfg.read_text()
        local = 'provider = "ollama"' in txt
        out.append(f"[{'ok' if local else 'CHECK'}] backend provider is local (ollama)")
        skillclaw_local = 'skillclaw_storage_backend = "local"' in txt
        out.append(f"[{'ok' if skillclaw_local else 'CHECK'}] SkillClaw storage local (air-gapped)")
    return out


TMPL = """# Self-Review — {ts}

## Automatic checks
{checks}

## Honest assessment
<two axes: how complete is the build, how confident am I — no inflation>

## Findings
- [severity] <finding> -> <concrete improvement>

## Ambiguities that may have slipped the gate
- <line> in <agent>: <residual reading> -> <suggested rewrite>
  (re-read each agent_built_prompts/*.prompt.md adversarially; can Ultron still reach a 2nd reading?)

## What will break first
- <component>: <why> -> <mitigation>

## Recommended next actions (user decides)
- 
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()
    checks = "\n".join(f"- {c}" for c in auto_checks(ws))
    (ws / "SELF_REVIEW.md").write_text(
        TMPL.format(ts=datetime.now(timezone.utc).isoformat(), checks=checks))
    print(f"Wrote {ws / 'SELF_REVIEW.md'} — now fill the findings honestly.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

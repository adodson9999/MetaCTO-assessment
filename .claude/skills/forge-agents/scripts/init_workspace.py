#!/usr/bin/env python3
"""
Scaffold the one self-contained foundry workspace.

Creates the folder tree from references/architecture.md, writes a starter
config.toml, and copies the installer in. Idempotent: safe to re-run.

Usage:
    python init_workspace.py [--name agent-foundry] [--dir .] [--provider ollama]
"""
from __future__ import annotations
import argparse
import shutil
from pathlib import Path

DIRS = [
    "agents/langgraph",
    "agents/crewai",
    "agents/claude_code_subagent",
    "agents/claude_sdk",
    "agent_built_prompts",
    "judge",
    "memory/.everos",
    "evolvers/skillopt",
    "evolvers/skillclaw",
    "results/runs",
    "vendor",
]

CONFIG_TMPL = """\
# Forge Agents — central config. One switch drives the whole foundry.

[backend]
# provider: "ollama" (local/air-gapped) or "claude-haiku" (cloud, opt-in)
provider = "{provider}"
ollama_base_url = "http://127.0.0.1:11434/v1"
ollama_model = "qwen2.5:14b-instruct"
claude_model = "claude-haiku-4-5"
litellm_proxy_url = "http://127.0.0.1:4000/v1"

[memory]
# Shared EverOS pool: all agents in the folder share project_id + app_id,
# each keeps its own agent_id so contributions stay attributable.
project_id = "{name}"
app_id = "forge"
everos_base_url = "http://127.0.0.1:8000"
store_path = "memory/.everos"

[search]
# Two-way hybrid: keyword (BM25/SQLite) + meaning (EverOS embeddings/LanceDB)
# fused by RRF, then a local reranker.
rrf_k = 60
reranker_model = "bge-reranker-v2-m3"   # local; runs offline

[sandbox]
# All agent read/write/exec confined here. Nothing escapes the workspace root.
enforce = true

[evolution]
# Nightly sleep cycle + manual /evolve. Gate = the judge metric. Staged, never auto-adopt.
schedule = "nightly"
skillclaw_storage_backend = "local"     # not OSS/S3 — stays air-gapped

[vendor]
# Filled in by /scan-and-integrate with pinned commits.
everos_commit = ""
skillopt_commit = ""
skillclaw_commit = ""
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--name", default="agent-foundry")
    ap.add_argument("--dir", default=".")
    ap.add_argument("--provider", default="ollama", choices=["ollama", "claude-haiku"])
    args = ap.parse_args()

    root = Path(args.dir).resolve() / args.name
    root.mkdir(parents=True, exist_ok=True)
    for d in DIRS:
        (root / d).mkdir(parents=True, exist_ok=True)

    cfg = root / "config.toml"
    if not cfg.exists():
        cfg.write_text(CONFIG_TMPL.format(provider=args.provider, name=args.name))

    # Copy installers next to the workspace if available beside this script.
    here = Path(__file__).resolve().parent
    for inst in ("install.sh", "install.ps1"):
        src = here / inst
        if src.exists():
            shutil.copy2(src, root / inst)

    # Seed empty leaderboard so the judge always has a target.
    lb = root / "results" / "leaderboard.json"
    if not lb.exists():
        lb.write_text('{"metric_name": null, "direction": null, "agents": {}, "runs": []}\n')

    print(f"Workspace ready: {root}")
    print("Next: run ./install.sh (or install.ps1), then /scan-and-integrate, then /forge-agents.")


if __name__ == "__main__":
    main()

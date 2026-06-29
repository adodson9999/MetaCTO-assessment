#!/usr/bin/env python3
"""
migrate_prompts.py
------------------
Consolidates per-framework prompt files into a single canonical source of truth.

Before: each workflow folder contains four identical .prompt.md files:
  api-tester-<workflow>.prompt.md  ← canonical (kept as-is)
  langgraph.prompt.md              ← duplicate
  crewai.prompt.md                 ← duplicate
  claude_sdk.prompt.md             ← duplicate

After: only the canonical file remains. The three framework files are removed.
Debate trail files (.debate.md) are left untouched.

Usage (run from agent-foundry/):
  python3 migrate_prompts.py [--dry-run]

Pass --dry-run to preview changes without touching anything.
"""

import os
import sys
from pathlib import Path

FRAMEWORK_FILES = {"langgraph.prompt.md", "crewai.prompt.md", "claude_sdk.prompt.md"}
DRY_RUN = "--dry-run" in sys.argv

base = Path(__file__).parent / "agent_built_prompts"

if not base.exists():
    print(f"ERROR: {base} not found. Run from agent-foundry/.")
    sys.exit(1)

deleted = []
skipped = []
errors = []

for workflow_dir in sorted(base.rglob("*")):
    if not workflow_dir.is_dir():
        continue

    # Find the canonical file in this folder (named api-tester-<workflow>.prompt.md or similar)
    all_prompts = list(workflow_dir.glob("*.prompt.md"))
    canonical = [f for f in all_prompts if f.name not in FRAMEWORK_FILES]
    frameworks = [f for f in all_prompts if f.name in FRAMEWORK_FILES]

    if not frameworks:
        continue  # nothing to do in this folder

    if not canonical:
        skipped.append(str(workflow_dir))
        print(f"SKIP  {workflow_dir.relative_to(base)} — no canonical file found, leaving untouched")
        continue

    canonical_file = canonical[0]
    canonical_content = canonical_file.read_text(encoding="utf-8")

    for fw_file in sorted(frameworks):
        fw_content = fw_file.read_text(encoding="utf-8")

        # Strip the header line (first non-empty line) from both and compare bodies
        canonical_body = "\n".join(
            line for i, line in enumerate(canonical_content.splitlines())
            if not (i == 0 and line.startswith("#"))
        ).strip()
        fw_body = "\n".join(
            line for i, line in enumerate(fw_content.splitlines())
            if not (i == 0 and line.startswith("#"))
        ).strip()

        if canonical_body != fw_body:
            errors.append(str(fw_file))
            print(f"DIFF  {fw_file.relative_to(base)} — body differs from canonical, SKIPPING")
            continue

        if DRY_RUN:
            print(f"[dry] DELETE {fw_file.relative_to(base)}")
        else:
            fw_file.unlink()
            print(f"DELETE {fw_file.relative_to(base)}")
        deleted.append(str(fw_file))

print()
print("=" * 60)
print(f"Deleted : {len(deleted)} files {'(dry run — nothing actually removed)' if DRY_RUN else ''}")
print(f"Skipped : {len(skipped)} folders (no canonical file)")
print(f"Errors  : {len(errors)} files (body differed — left untouched)")

if errors:
    print()
    print("Files with differing content (inspect manually):")
    for e in errors:
        print(f"  {e}")

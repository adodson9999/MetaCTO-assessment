# Installing this update

Writes into `.claude/skills/` are blocked in this session (skills are read-only
there), so this package was built in the outputs folder. To apply it:

1. **Back up** your current skill:
   `cp -r .claude/skills/forge-agents .claude/skills/forge-agents.bak`

2. **Copy these files in.** Place `SKILL.md`, `references/`, and `scripts/` from
   this package at the **skill root** — i.e. `.claude/skills/forge-agents/SKILL.md`,
   `.claude/skills/forge-agents/references/...`, `.claude/skills/forge-agents/scripts/...`.
   This also fixes the double-nesting: there should be exactly one `SKILL.md`, at the
   root. Remove the stray inner `forge-agents/forge-agents/` once content is merged.

3. **Keep your existing references/scripts** that this package does not replace
   (debate-gate.md, judge.md, evolution.md, architecture.md, agent-frameworks.md,
   memory-everos.md, self-review.md, init_workspace.py, run_agents.py, etc.). This
   package only adds/updates files; it does not delete the originals.

4. **New files are additive.** The new `references/*.md` and `scripts/*.py` plug
   into the existing flow via SKILL.md. No existing script signature changed.

5. **Sanity check** (once your bash sandbox is available):
   `python3 -m py_compile scripts/*.py`
   `python3 scripts/slop_scan.py scripts --json`   # should score the scripts
   `python3 scripts/forge.py help`

Nothing here calls the network; all new scripts are Python stdlib only.

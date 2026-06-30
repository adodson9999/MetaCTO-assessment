# The `forge` CLI (thin wrapper)

The skill is the brain; the CLI is a thin, deterministic wrapper over the same
scripts so the workflow is usable from a terminal and from CI (built for the
simplest model — the CLI does, it does not reason). Every command maps 1:1 to a
script already in the workspace. Routine commands run **without asking permission**;
the only halts are the debate gate and a guardrail failure (constitution
Article V).

| Command                       | Runs                          | Phase |
|-------------------------------|-------------------------------|-------|
| `forge init [--name N]`       | `scripts/init_workspace.py`   | 1 |
| `forge specify`               | task interview helper         | 2 |
| `forge data <path>`           | `scripts/data_profile.py`     | 2.2 |
| `forge build`                 | author agents (debate gate)   | 3 |
| `forge analyze`               | `scripts/analyze.py`          | 3.5 |
| `forge judge`                 | `scripts/run_agents.py` + judge | 4 |
| `forge improve [--rounds 10]` | `scripts/improve_loop.py`     | 4.5 |
| `forge evolve`                | SkillOpt/SkillClaw trigger    | 5 |
| `forge verify [--phase N]`    | `scripts/verify_build.py`     | 4 & 6 |
| `forge code-review-gate`      | `scripts/code_review_gate.py` | 6.5 |
| `forge test [<group>/<name>]` | `scripts/golden_run.py`       | 6 |
| `forge determinism <artifact>`| `scripts/determinism_check.py`| any |
| `forge preset|extension add`  | customization layering        | any |

## Conventions

- Exit code is the contract: `0` = pass, non-zero = a guardrail/gate failure that
  hard-halts the calling flow.
- `forge build-all` runs init → specify → (data) → build → analyze → judge →
  improve → verify → test in order, stopping at the first non-zero exit.
- No command writes outside `FORGE_WORKSPACE`.
- The CLI is optional sugar; the slash commands (`/forge-agents`, `/evolve`,
  `/forge-test`, `/analyze`) drive the same scripts for users inside Claude Code.

# File-Completeness Guardrail — every created file, verified

You should never have to ask "was `.claude/agents/<name>.md` actually created?"
again. This guardrail verifies that **every file the build is supposed to produce
exists and contains correct information** — not just the agent registration, but
every artifact across the whole workspace. It is part of the output contract
(constitution Article I.9) and runs inside `verify_build.py`.

Enforcer: `scripts/verify_files.py`. It works two ways, and uses both:

1. **Derived expected-set (deterministic).** From the agents present in the
   workspace, it derives the canonical set of files that *must* exist for each
   agent and globally, and checks each one.
2. **Build manifest (recorded).** The foundry appends every file it writes to
   `workspace/BUILD_MANIFEST.json` as it goes. The verifier confirms every
   manifest entry exists and passes its content check, and that nothing in the
   derived set is missing from disk.

A missing file, an empty file, or a file whose content fails its check is an
output-contract failure → **hard-halt and ask the user**.

## What "correct information" means per file kind

| File | Existence + content check |
|------|---------------------------|
| `agents/<g>/<n>/{langgraph,crewai,claude_sdk,subagent}/run.py` | exists, non-empty, is a **thin dispatcher** (imports from `runners.*`, no inline framework boilerplate) |
| `agents/<g>/<n>/subagent/<n>.md` | exists, valid YAML frontmatter with `name:` (matching `<n>`) + `description:`, non-empty gated body |
| **`.claude/agents/<n>.md`** (host repo root) | exists as a **symlink (or file)** that **resolves** to the canonical `agents/<g>/<n>/subagent/<n>.md`; `name:` frontmatter, filename, and symlink all match |
| `judge/<g>/<n>/metric.json` | parses as JSON; has `metric_name`, `direction`, `emit_fields` |
| `judge/<g>/<n>/score.py` | exists, non-empty, defines a scoring entrypoint |
| `results/<g>/<n>/leaderboard-<ts>.json` / `.md` | at least one timestamped pair; JSON parses; no bare `leaderboard.json` |
| `results/runs/<id>/<framework>.json` | parses; carries the 6 required metric fields, `metric_value` numeric |
| `tests/golden/<g>/<n>/golden.json` | parses; has `baseline` + `cases` |
| `config.toml` | exists; `[backend].provider = "auto"` |
| `memory/.everos/` | directory exists (shared pool) |
| `workspace/SELF_REVIEW.md` | exists, non-empty |
| `results/_global/analyze-<ts>.json` | exists, `status: pass` |
| `results/_global/determinism/*.json` | at least one receipt, none `non-deterministic` |
| `results/_global/quality-<ts>.json` | overall score ≥ 95 |

Any additional files the foundry creates (data profiles, extra runners, preset
overrides) are covered by the manifest entries it records for them.

## The `.claude/agents/` registration — explicit

Because Claude Code discovers a subagent only when it is registered at the host
repo's `.claude/agents/`, `verify_files.py` checks this **specifically and loudly**:

- the path `<host-repo>/.claude/agents/<n>.md` exists,
- it resolves (if a symlink) to `agents/<g>/<n>/subagent/<n>.md`,
- the target's `name:` equals `<n>` and the filename matches.

If it is missing, the verifier does not silently pass — it reports
`MISSING .claude/agents/<n>.md` and hard-halts. The host repo root is the parent
of the foundry workspace (`agent-foundry/` lives at `<repo>/agent-foundry/`).

## Exactly one registry — no `agent-foundry/.claude/agents/`

There must be **one** subagent registry, at the **host repo root**
(`<repo>/.claude/agents/`). A `.claude/agents/` **inside** the foundry workspace
(`<repo>/agent-foundry/.claude/agents/`) is a **stray second registry** and a
defect: Claude Code (with the project root = repo) never reads it, the canonical
prompts already live at `agents/<name>/subagent/<name>.md`, and the duplicate only
causes drift (e.g. some entries become standalone real-file copies instead of
symlinks, which then silently diverge from the canonical prompt).

`verify_files.py` therefore **fails the build if `<workspace>/.claude/agents/`
exists** — it reports `agent-foundry/.claude/agents/ exists … stray second
registry; remove it.` Keep the single host-root registry; delete the foundry-local
one. (Bonus check: any entry in the host-root registry that is a plain file rather
than a symlink resolving to its canonical prompt is flagged as an unmanaged
duplicate.)

## BUILD_MANIFEST.json format

The foundry appends one line per file it creates:

```json
{
  "files": [
    {"path": "agents/api-tester/create-postman-collection/subagent/create-postman-collection.md",
     "kind": "agent_prompt", "by": "phase3"},
    {"path": ".claude/agents/create-postman-collection.md",
     "kind": "subagent_registration", "target": "agents/.../subagent/create-postman-collection.md"},
    {"path": "judge/api-tester/create-postman-collection/metric.json", "kind": "metric"}
  ]
}
```

`verify_files.py` validates each `kind` with the matching content check above. The
manifest catches anything the derived set can't know about; the derived set catches
anything the foundry forgot to record. Together they guarantee **completeness**.

## Output

`results/_global/files-<ts>.json`:
```json
{"status": "pass|fail", "ts": "...", "checked": 42,
 "missing": [], "bad_content": [], "registration_ok": true}
```

`verify_build.py` requires `status: pass` (new guardrails item) before any build
reports "done".

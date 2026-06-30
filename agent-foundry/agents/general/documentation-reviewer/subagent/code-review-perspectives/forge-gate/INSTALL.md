# Install the Code-Review Gate into forge-agents

This session can't write into `.claude/skills/forge-agents/` (skill folders are
protected), so this package ships the gate as drop-in files plus the exact edits
to apply. All paths below are relative to your skill root:
`.claude/skills/forge-agents/`.

## 1. Copy the four new files

| From (this folder)              | To (in the skill)                              |
|---------------------------------|------------------------------------------------|
| `code-review-gate.md`           | `references/code-review-gate.md`               |
| `code_review_gate.py`           | `scripts/code_review_gate.py`                  |
| `test_code_review_gate.py`      | `tests/test_code_review_gate.py`               |
| `code-review-gate.golden.json`  | `tests/golden/code-review-gate.golden.json`    |

(Create `tests/` and `tests/golden/` if they don't exist.)

Prerequisite: the code-review reviewers must already be built into
`agents/code-review/<short>/subagent/code-review-<short>.md` (use
`../forge-starters.md`). The gate discovers whatever reviewers are in that folder at
run time and hard-errors (exit 2) if the folder is empty.

## 2. Five edits to existing skill files

### 2a. `references/constitution.md` — add invariant Article I.10

After Article I.9, add:

```markdown
10. **Code-producing builds pass the code-review gate at ≥85, no exception.** Any
    code file the build creates — and, when the built agent is code-producing (QA
    automation, software engineer, codegen, refactor), the code that agent
    produces — must score **≥ 85 on every code-review agent present in
    `agents/code-review/`** (the set discovered at run time, however many — no fixed
    count) before the build reports "done". The threshold is a floor: it may be
    raised, never lowered, and the gate is never waived. Enforced
    by `scripts/code_review_gate.py`; verified by `verify_build.py` (a passing
    `results/_global/code-review-<TS>.json` receipt). See
    `references/code-review-gate.md`.
```

### 2b. `references/guardrails.md` — add a deliverable-contract item

Under "The deliverable contract", add item 9:

```markdown
### 9. Code-review gate (Article I.10)
- `results/_global/code-review-<TS>.json` exists (the gate always runs and writes a receipt).
- The receipt's reviewer set equals the current contents of `agents/code-review/`
  (no stale or short-receipt bypass).
- When `applies` is true, `status` must be `pass`: every created code file — and the
  agent's produced code when it is code-producing — scored ≥ 85 on **every reviewer
  discovered in `agents/code-review/`** (however many). Any rating below 85, any
  missing reviewer/target, or an empty reviewer set hard-halts the build. Threshold
  is a floor (never lowered), the gate is never waived. See
  `references/code-review-gate.md`.
```

### 2c. `SKILL.md` — add the phase and the spec-kit table row

In the "How this maps to spec-kit" table, add a row (after the `checklist` row):

```markdown
| checklist           | **Phase 6.5 — code-review gate**             | every reviewer in agents/code-review/ ≥85 over all created/produced code |
```

In "### Phase 6 — Verify, self-review, and golden suite", add a 4th completion
step:

```markdown
4. **Code-review gate (Phase 6.5, code-producing builds)** —
   `scripts/code_review_gate.py --agent <group>/<name>` discovers and runs every
   reviewer in `agents/code-review/` (however many) over every code file the build
   created (and the agent's produced code when it is code-producing). Pass = every
   target scores ≥ 85 on every discovered reviewer. On any sub-85 score: hard-halt,
   show the reviewer's notes, rewrite the code (never waive, never lower), re-run.
   See `references/code-review-gate.md`.
```

### 2d. `references/cli.md` — add the command row

```markdown
| `forge code-review-gate`      | `scripts/code_review_gate.py` | 6.5 |
```

### 2e. `scripts/verify_build.py` — recognize the group + check the receipt

1. Add `"code-review"` to the agent groups in `agent_dirs()`:

```python
def agent_dirs(ws: Path) -> list[Path]:
    out = []
    for group in ("api-tester", "general", "code-review"):   # <- add code-review
        gdir = ws / "agents" / group
        if gdir.is_dir():
            out += [d for d in gdir.iterdir() if d.is_dir()]
    return out
```

2. Add this check function:

```python
def check_code_review_gate(ws: Path, r: Report) -> None:
    import sys as _sys
    _sys.path.insert(0, str(ws / "scripts"))
    try:
        import code_review_gate as crg
    except Exception:
        crg = None
    receipts = sorted(glob.glob(str(ws / "results" / "_global" / "code-review-*.json")))
    r.check(bool(receipts), "code-review gate receipt",
            "no results/_global/code-review-*.json (gate not run)")
    if not receipts:
        return
    try:
        data = json.loads(Path(receipts[-1]).read_text())
    except Exception as e:
        r.check(False, "code-review gate receipt parseable", str(e))
        return
    applies = bool(data.get("applies"))
    status = data.get("status")
    r.check((not applies) or status == "pass",
            "code-review gate >=85 (every reviewer in agents/code-review/, no exception)",
            f"status={status}, min_rating={data.get('min_rating')}; rewrite code below 85")
    # no-bypass: the receipt's reviewer set must equal the current folder contents
    if applies and crg is not None:
        r.check(crg.receipt_matches_folder(data, ws),
                "code-review reviewer set matches agents/code-review/",
                "receipt reviewer set != folder (stale/short receipt) — re-run the gate")
```

3. Call it in `main()` inside the `if args.phase == 6:` block:

```python
    if args.phase == 6:
        check_leaderboards(ws, r)
        check_phase6_extras(ws, r)
        check_files(ws, r)
        check_quality(ws, r)
        check_code_review_gate(ws, r)      # <- add this line
```

## 3. Optional config (in the generated `agent-foundry/config.toml`)

```toml
[code_review_gate]
applies = false   # leave unset to auto-detect code-producing agents from task_spec;
                  # set true to force the gate for this build
threshold = 85    # floor; may be raised, never lowered
```

## 4. Verify the install

```bash
pytest -q tests/test_code_review_gate.py        # gate logic + golden cases
python scripts/code_review_gate.py --agent code-review/minimalist --workspace . --dry-run
python scripts/verify_build.py --phase 6 --workspace .   # now includes the gate receipt check
```

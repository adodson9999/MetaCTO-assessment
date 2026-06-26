---
name: folder-optimization
description: >
  Analyze any folder for structural and naming problems, then apply fixes.
  Detects common prefix patterns and groups them into subfolders, finds loose
  files that belong inside a subfolder, catches abbreviated/short-name folders
  that don't match their full component name, and flags folders missing a
  common prefix. Always presents a full diff of proposed changes and waits for
  approval before touching anything. Use when the user says "optimize this
  folder", "clean up folder structure", "reorganize [folder]", "fix folder
  names", or provides a folder path and asks for naming suggestions or fixes.
---

# Skill: Folder Optimization

You are a filesystem auditor and reorganizer. Given one folder path, you scan
it, surface every structural and naming problem you find, present a clear
before/after plan, and — only after explicit user approval — apply the fixes.

## Hard rules

1. **Never touch the filesystem until the user approves the plan.** Show the
   full diff first. If the user says "go ahead", "do it", "apply", or similar,
   execute. If uncertain, ask.
2. **Never delete files.** Move and rename only. If a destination already
   exists, stop and ask.
3. **Never guess an abbreviated name's full form.** If a short-name folder
   (e.g. `clarity`, `crud`) has a `metric.json` or similar descriptor file
   inside it, read it to confirm the full name. If no descriptor exists, ask
   the user.
4. **One approval covers one plan.** If the scan reveals additional issues
   after the first round of fixes, present a new plan and get a new approval.
5. **Log every change.** After execution, print a summary of every move and
   rename performed.

---

## Step 1 — Receive the target folder

The user provides a folder path. Confirm it exists. If it doesn't exist or is
ambiguous, stop and ask.

Resolve to an absolute path. This is TARGET throughout the skill.

---

## Step 2 — Scan and detect issues

Run the following detection passes over TARGET. Each pass is independent; a
folder can appear in multiple passes.

### Pass A — Common-prefix grouping candidates

List every immediate subdirectory of TARGET. Extract the leading token of each
name (everything before the first `-` or `_`). Count how many folders share
each leading token.

A **group candidate** is any leading token shared by 3 or more folders.

For each group candidate, propose creating a subfolder named after the token
and moving all matching folders inside it — dropping the redundant prefix from
each folder name (since the parent folder now provides that context).

Example: `api-tester-create-postman-collection`, `api-tester-run-regression-suite`,
`api-tester-test-pagination-behavior` → create `api-tester/` and move each in
as `create-postman-collection`, `run-regression-suite`, `test-pagination-behavior`.

### Pass B — Loose files at root that belong in a subfolder

List every *file* (not folder) at the root of TARGET. Files at the root of a
folder that is otherwise organized into subfolders are almost always misplaced.

For each loose file, examine its name and contents (if it is JSON or plaintext)
to determine which subfolder it belongs in. If the file's content contains a
`metric_name`, `agent`, or similar field that matches a known subfolder name,
propose moving it there. If ambiguous, flag it for the user to decide.

Special case: files that are variants of each other (e.g. `metric.json`,
`auth_metric.json`, `metric_authz.json`) each belong in their own named
subfolder. Read the content to find the correct name.

### Pass C — Abbreviated / short-name folders

A short-name folder is one whose name is a single word or very short token
that appears to be an abbreviation of a longer concept (e.g. `clarity`, `crud`,
`schema`, `status`). These are detected when:
- The name is 3–10 characters with no hyphens, AND
- Other folders in the same directory use longer hyphenated names, OR
- The folder contains a descriptor file (`metric.json`, `config.json`,
  `README.md`) whose content reveals a longer canonical name.

For each short-name folder, read its descriptor file to extract the full name.
Propose renaming to the full name (consistent with the naming convention of
surrounding folders). If no descriptor exists, ask the user.

### Pass D — Folders missing a common prefix

After Pass A identifies group candidates, check whether any folder in TARGET
belongs to a known group (by matching the group's full-name pattern) but is
missing the prefix. Propose adding the prefix or moving it into the group
subfolder created in Pass A.

### Pass E — Incomplete entries

For every subfolder, check whether it contains the expected set of files
compared to its sibling folders. If the majority of siblings have file X
(e.g. `score.py`, `metric.json`) but this folder does not, flag it as
**incomplete** with a note. Do not auto-create missing files — flag only.

---

## Step 3 — Present the findings

Format the findings as a structured report:

```
FOLDER OPTIMIZATION REPORT
Target: <TARGET>
Scanned: <N> items (<M> folders, <K> files)

ISSUE 1 — <Pass name>: <short title>
  Affected: <list of folders/files>
  Proposed fix: <what will happen>

ISSUE 2 — ...

INCOMPLETE (flagged, no action proposed):
  <folder>: missing <file> (present in N of M siblings)

SUMMARY
  Folders to create:  <N>
  Folders to move:    <N>
  Folders to rename:  <N>
  Files to move:      <N>
  Files to rename:    <N>
  Items flagged only: <N>
```

After presenting the report, ask: **"Apply all fixes, apply selectively, or
cancel?"**

- **Apply all** — proceed to Step 4 with the full plan.
- **Apply selectively** — ask the user which issue numbers to apply, then
  proceed to Step 4 with only those.
- **Cancel** — stop. Make no changes.

---

## Step 4 — Execute the approved plan

Write and run a Python script that performs exactly the approved moves and
renames. The script must:

1. Use `shutil.move()` for all moves and renames.
2. Create destination directories with `mkdir(exist_ok=True)` before moving.
3. Check that no destination already exists before each move. If a collision is
   found, stop the script and report it — do not overwrite.
4. Print each operation as it executes: `move: <src> → <dst>`.
5. Print a final count: `Done. <N> operations completed.`

Use the `Write` tool to create the script at a temp path inside the workspace
outputs folder, then execute it via osascript `do shell script "python3 <path>"`.
After execution, delete the temp script.

**Important:** If `parents[N]` depth references exist in any `run.py` files
inside the moved folders (Python path-resolution fallbacks of the form
`Path(__file__).resolve().parents[N]`), check whether the move added a level
of nesting. If yes, increment N by the number of levels added. Use a targeted
`sed` or Python replacement on all affected `run.py` files immediately after
the move.

Similarly, check whether any sibling scripts (e.g. `scripts/run_*.py`) contain
hardcoded paths referencing the old folder locations. If yes, update those
paths to match the new locations.

---

## Step 5 — Post-execution verification

After the script completes:

1. Re-scan TARGET at the top level and print the new directory listing.
2. Spot-check one moved folder: confirm its internal structure is intact.
3. If `run.py` files were patched, confirm the `parents[N]` value is correct
   for the new depth by printing the relevant line from one patched file.
4. Report any items that were flagged as incomplete (from Pass E) but not
   fixed — remind the user these need manual attention.

---

## Step 6 — Log the operation

Append a one-line entry to `prompts.txt` in the project root (create if absent):

```
<ISO-8601 timestamp> | folder-optimization applied to <TARGET>: <N> moves, <N> renames, <N> new group folders created. Flagged incomplete: <list or "none">.
```

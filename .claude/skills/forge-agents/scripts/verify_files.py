#!/usr/bin/env python3
"""File-completeness guardrail — every created file exists with correct content.

So you never again have to ask "was .claude/agents/<name>.md created?". Derives the
canonical expected-set from the agents present, validates each file's content, and
ALSO validates every entry recorded in workspace/BUILD_MANIFEST.json. Checks the
.claude/agents/ registration symlink explicitly. (references/file-verification.md)

Usage: python scripts/verify_files.py [--workspace DIR]
Exit 0 = every file present + correct, 1 = missing or bad-content.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


class V:
    def __init__(self) -> None:
        self.missing: list[str] = []
        self.bad: list[str] = []
        self.checked = 0
        self.registration_ok = True

    def exists(self, p: Path, label: str | None = None) -> bool:
        self.checked += 1
        if not p.exists():
            self.missing.append(label or str(p))
            return False
        return True

    def nonempty(self, p: Path) -> bool:
        if p.exists() and p.stat().st_size == 0:
            self.bad.append(f"{p} (empty)")
            return False
        return True

    def json_ok(self, p: Path, keys: list[str]) -> None:
        if not self.exists(p):
            return
        try:
            data = json.loads(p.read_text())
        except Exception as e:
            self.bad.append(f"{p} (unparseable json: {e})")
            return
        missing = [k for k in keys if k not in data]
        if missing:
            self.bad.append(f"{p} (missing keys {missing})")

    def frontmatter(self, p: Path, name: str) -> None:
        if not self.exists(p):
            return
        text = p.read_text(errors="replace")
        if not text.lstrip().startswith("---"):
            self.bad.append(f"{p} (no YAML frontmatter)")
            return
        if f"name: {name}" not in text and f"name:{name}" not in text:
            self.bad.append(f"{p} (frontmatter name != {name})")
        body = text.split("---", 2)[-1].strip()
        if len(body) < 40:
            self.bad.append(f"{p} (gated body too short / empty)")

    def thin_dispatcher(self, p: Path) -> None:
        if not self.exists(p) or not self.nonempty(p):
            return
        src = p.read_text(errors="replace")
        if "runners." not in src and "build_invoker" not in src:
            self.bad.append(f"{p} (run.py not a thin dispatcher — must import runners.*)")


def agents(ws: Path):
    for group in ("api-tester", "general"):
        for d in glob.glob(str(ws / "agents" / group / "*")):
            yield group, Path(d).name


def check_registration(ws: Path, group: str, name: str, v: V) -> None:
    host = ws.parent  # foundry lives at <repo>/agent-foundry/
    reg = host / ".claude" / "agents" / f"{name}.md"
    canonical = ws / "agents" / group / name / "subagent" / f"{name}.md"
    v.checked += 1
    if not reg.exists():
        v.missing.append(f".claude/agents/{name}.md (subagent NOT registered)")
        v.registration_ok = False
        return
    try:
        if reg.is_symlink():
            target = (reg.parent / Path(reg).readlink()).resolve()
            if canonical.resolve() != target:
                v.bad.append(f".claude/agents/{name}.md (symlink target != canonical prompt)")
                v.registration_ok = False
    except OSError as e:
        v.bad.append(f".claude/agents/{name}.md (symlink error: {e})")
        v.registration_ok = False


def check_no_foundry_registry(ws: Path, v: V) -> None:
    """There must be exactly ONE subagent registry, at the host repo root.

    A `.claude/agents/` INSIDE the foundry workspace is a stray second registry:
    Claude Code (project root = repo) never reads it, the canonical prompts live in
    `agents/<name>/subagent/<name>.md`, and a duplicate only causes drift/confusion.
    Its presence is a defect.
    """
    stray = ws / ".claude" / "agents"
    v.checked += 1
    if stray.exists():
        n = len(list(stray.glob("*.md")))
        v.bad.append(f"agent-foundry/.claude/agents/ exists ({n} entries) — stray "
                     f"second registry; remove it. The only registry is the host "
                     f"repo root .claude/agents/.")


def check_globals(ws: Path, v: V) -> None:
    v.exists(ws / "config.toml")
    v.exists(ws / "memory" / ".everos", "memory/.everos/")
    se = ws / "workspace" / "SELF_REVIEW.md"
    v.exists(se if se.exists() else ws / "SELF_REVIEW.md", "SELF_REVIEW.md")


def check_each_agent(ws: Path, v: V) -> bool:
    found_any = False
    for group, name in agents(ws):
        found_any = True
        base = ws / "agents" / group / name
        for fw in ("langgraph", "crewai", "claude_sdk", "subagent"):
            v.thin_dispatcher(base / fw / "run.py")
        v.frontmatter(base / "subagent" / f"{name}.md", name)
        check_registration(ws, group, name, v)
        v.json_ok(ws / "judge" / group / name / "metric.json",
                  ["metric_name", "direction", "emit_fields"])
        v.exists(ws / "judge" / group / name / "score.py")
        if not glob.glob(str(ws / "results" / group / name / "leaderboard-*.json")):
            v.missing.append(f"results/{group}/{name}/leaderboard-*.json")
        v.json_ok(ws / "tests" / "golden" / group / name / "golden.json",
                  ["baseline", "cases"])
    if not found_any:
        v.missing.append("agents/<group>/<name>/ (no agents found)")
    return found_any


def check_manifest(ws: Path, v: V) -> None:
    man = ws / "workspace" / "BUILD_MANIFEST.json"
    if not man.exists():
        return
    try:
        entries = json.loads(man.read_text()).get("files", [])
    except Exception as e:
        v.bad.append(f"BUILD_MANIFEST.json unparseable: {e}")
        return
    for entry in entries:
        rel = entry["path"]
        if rel.startswith("/"):
            p = Path(rel)
        elif rel.startswith(".claude/"):
            p = ws.parent / rel  # host-root registry
        else:
            p = ws / rel
        if not p.exists():
            v.missing.append(f"{rel} (in manifest, not on disk)")
        else:
            v.checked += 1


def write_report(ws: Path, v: V) -> int:
    status = "pass" if not v.missing and not v.bad else "fail"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = ws / "results" / "_global"
    out.mkdir(parents=True, exist_ok=True)
    rec = {"status": status, "ts": ts, "checked": v.checked,
           "missing": v.missing, "bad_content": v.bad,
           "registration_ok": v.registration_ok}
    (out / f"files-{ts}.json").write_text(json.dumps(rec, indent=2))
    print(f"verify_files  ({ws})  checked={v.checked}")
    for m in v.missing:
        print(f"  MISSING  {m}")
    for b in v.bad:
        print(f"  BAD      {b}")
    if status == "fail":
        print(f"\n{len(v.missing)} missing, {len(v.bad)} bad. HARD-HALT: "
              f"create/fix every file before reporting 'done'.")
        return 1
    print("\nall expected files present and well-formed.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    v = V()
    check_no_foundry_registry(ws, v)  # exactly one registry, at the repo root
    check_globals(ws, v)
    check_each_agent(ws, v)
    check_manifest(ws, v)
    return write_report(ws, v)


if __name__ == "__main__":
    sys.exit(main())

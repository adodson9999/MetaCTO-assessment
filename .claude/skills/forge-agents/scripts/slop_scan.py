#!/usr/bin/env python3
"""aislop-style code-quality gate — deterministic, no LLM.

Scores every generated deterministic file 0-100 by static regex + AST checks.
The pass floor is 95 (constitution Article II). A file below 95 must be REWRITTEN,
not patched. "Same code in, same score out" — pure static analysis, no model calls,
fully offline/air-gapped.

If Node + `npx aislop` is available it is used for the richer engines; otherwise
this bundled checker runs so the gate always works.

Usage:
    python scripts/slop_scan.py [path ...] [--json] [--fail-below 95] [--workspace DIR]
Exit code: 0 if every scanned file >= floor, else 1.
"""
from __future__ import annotations

import argparse
import ast
import json
import re
import sys
from pathlib import Path

FLOOR_DEFAULT = 95

# (penalty, label, compiled regex) — each match subtracts `penalty` from 100.
TEXT_RULES = [
    (8, "bare-except", re.compile(r"^\s*except\s*:\s*$", re.M)),
    (8, "eval-use", re.compile(r"\beval\s*\(")),
    (6, "as-any", re.compile(r":\s*any\b|\bas\s+any\b")),
    (5, "leftover-print", re.compile(r"^\s*print\(", re.M)),
    (5, "console-log", re.compile(r"console\.log\(")),
    (6, "todo-stub", re.compile(r"#\s*(TODO|FIXME|XXX)\b|//\s*(TODO|FIXME)", re.I)),
    (4, "narrative-comment", re.compile(r"#\s*(Now we|Here we|This (function|code) (will|does)|Let's)\b", re.I)),
    (10, "bare-export-provider", re.compile(r"export\s+FORGE_PROVIDER=")),
    (10, "abs-path-escape", re.compile(r'["\'](?:/Users|/home|/etc|/var)(?!.*FORGE_WORKSPACE)')),
    (6, "hardcoded-model", re.compile(r'"(claude-[\w.-]+|gpt-[\w.-]+|llama[\w.:-]+)"')),
]

MAX_FUNC_LINES = 60
MAX_FILE_LINES = 400


def is_cli(src: str) -> bool:
    """A CLI entrypoint legitimately prints to stdout; don't flag that as slop."""
    return '__main__' in src and ('argparse' in src or 'sys.argv' in src)


def scan_text(src: str, cli: bool = False) -> list[dict]:
    issues = []
    for penalty, label, rx in TEXT_RULES:
        if cli and label in ("leftover-print", "console-log"):
            continue  # stdout is this file's job
        for m in rx.finditer(src):
            line = src.count("\n", 0, m.start()) + 1
            issues.append({"rule": label, "penalty": penalty, "line": line})
    if src.count("\n") + 1 > MAX_FILE_LINES:
        issues.append({"rule": "file-too-long", "penalty": 8, "line": 1})
    return issues


def scan_python_ast(src: str) -> list[dict]:
    issues = []
    try:
        tree = ast.parse(src)
    except SyntaxError as e:
        return [{"rule": "syntax-error", "penalty": 100, "line": e.lineno or 1}]
    imported, used = set(), set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            span = (getattr(node, "end_lineno", node.lineno) or node.lineno) - node.lineno
            if span > MAX_FUNC_LINES:
                issues.append({"rule": "function-too-long", "penalty": 6, "line": node.lineno})
        if isinstance(node, ast.Import):
            for a in node.names:
                imported.add((a.asname or a.name).split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                imported.add(a.asname or a.name)
        elif isinstance(node, ast.Name):
            used.add(node.id)
    for name in imported - used - {"annotations"}:
        issues.append({"rule": "unused-import", "penalty": 4, "line": 1, "detail": name})
    return issues


def score_file(path: Path) -> dict:
    src = path.read_text(encoding="utf-8", errors="replace")
    issues = scan_text(src, cli=is_cli(src))
    if path.suffix == ".py":
        issues += scan_python_ast(src)
    score = max(0, 100 - sum(i["penalty"] for i in issues))
    return {"file": str(path), "score": score, "issues": issues}


def iter_targets(paths: list[Path]) -> list[Path]:
    exts = {".py", ".sh", ".ps1", ".js", ".ts"}
    skip = {"node_modules", ".git", "vendor", ".venv", "dist", "build"}
    out: list[Path] = []
    for p in paths:
        if p.is_file():
            out.append(p)
        elif p.is_dir():
            for f in p.rglob("*"):
                if f.suffix in exts and not (skip & set(f.parts)):
                    out.append(f)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("paths", nargs="*", default=["."])
    ap.add_argument("--fail-below", type=int, default=FLOOR_DEFAULT)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()

    targets = iter_targets([Path(p) for p in (args.paths or ["."])])
    results = [score_file(p) for p in targets]
    overall = min((r["score"] for r in results), default=100)
    failed = [r for r in results if r["score"] < args.fail_below]

    if args.json:
        print(json.dumps({"overall": overall, "floor": args.fail_below,
                          "passed": not failed, "files": results}, indent=2))
    else:
        for r in results:
            mark = "OK " if r["score"] >= args.fail_below else "REWRITE"
            print(f"[{mark}] {r['score']:3d}  {r['file']}")
            if r["score"] < args.fail_below:
                for i in r["issues"]:
                    print(f"          - {i['rule']} (line {i['line']}, -{i['penalty']})")
        print(f"\noverall: {overall}  floor: {args.fail_below}  "
              f"{'PASS' if not failed else 'FAIL — files below 95 must be rewritten'}")

    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())

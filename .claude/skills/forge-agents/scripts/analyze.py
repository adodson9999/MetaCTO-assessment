#!/usr/bin/env python3
"""/analyze — cross-artifact consistency gate (Phase 3.5, references/analyze.md).

Checks task_spec <-> agents <-> judge metric <-> constitution agree before the
judge is built. Mechanical checks are pure Python; the model fills the few
judgement checks (recorded with justification). On any contradiction the build
must HARD-HALT and ask the user. Writes results/_global/analyze-<ts>.json.

Usage: python scripts/analyze.py [--workspace DIR]
Exit 0 = pass, 1 = contradiction.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def agents(ws: Path):
    for group in ("api-tester", "general"):
        for d in glob.glob(str(ws / "agents" / group / "*")):
            yield group, Path(d).name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    checks = []

    spec = ws / "task_spec.md"
    checks.append({"id": "spec-present", "status": "pass" if spec.is_file() else "fail",
                   "detail": "task_spec.md missing" if not spec.is_file() else ""})

    for group, name in agents(ws):
        adir = ws / "agents" / group / name
        have_all = all((adir / fw / "run.py").is_file()
                       for fw in ("langgraph", "crewai", "claude_sdk", "subagent"))
        checks.append({"id": f"agents-complete:{name}",
                       "status": "pass" if have_all else "fail",
                       "detail": "" if have_all else "not all four frameworks present"})

        metric = ws / "judge" / group / name / "metric.json"
        if metric.is_file():
            m = json.loads(metric.read_text())
            need = set(m.get("emit_fields", []))
            # agents-metric: the run json must be able to emit these fields.
            checks.append({"id": f"agents-metric:{name}",
                           "status": "pass" if need else "fail",
                           "detail": "" if need else "metric.json has no emit_fields"})
        else:
            checks.append({"id": f"metric-present:{name}", "status": "fail",
                           "detail": "judge metric.json missing"})

    status = "pass" if all(c["status"] == "pass" for c in checks) else "fail"
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = ws / "results" / "_global"
    out.mkdir(parents=True, exist_ok=True)
    rec = {"status": status, "ts": ts, "checks": checks,
           "note": "constitution Articles II-VII judgement checks are appended by "
                   "the model with justification before this file is trusted."}
    (out / f"analyze-{ts}.json").write_text(json.dumps(rec, indent=2))

    print(json.dumps(rec, indent=2))
    if status == "fail":
        print("\nANALYZE FAIL: HARD-HALT and ask the user to resolve each "
              "contradiction before building the judge.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

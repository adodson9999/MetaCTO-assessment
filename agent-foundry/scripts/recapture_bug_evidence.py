#!/usr/bin/env python3
# Used by: manual/finalize — re-capture REAL evidence for every bug in a dated deliverable tree.
"""Re-capture screenshot(PNG)/recording(cast)/log(server) evidence for every bug report under a
dated BugReport tree, replacing the old placeholder artifacts (text 'replay' screenshots, static
casts, agent-stdout logs). Updates each report's attachments + artifact_completeness and, for
verified bugs, regenerates the markdown.

Usage:
    FORGE_WORKSPACE=... python recapture_bug_evidence.py <out_root> <target> [server_log]

<out_root>   e.g. agent-foundry/results/2026-07-03/18-10-17
<target>     the LIVE logging server, e.g. http://localhost:8890
[server_log] path to that server's stdout log (for best-effort server-log capture)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
import capture_evidence as CE  # noqa: E402
import build_deliverables as BD  # noqa: E402


def _ts_from_run(run_id: str) -> int:
    # deterministic epoch from the run date/time (no wall clock)
    import datetime
    from bugreport import run_date_time  # noqa: E402
    d, t = run_date_time(run_id)
    y, mo, da = (int(x) for x in d.split("-"))
    h, mi, s = (int(x) for x in t.split("-"))
    return int(datetime.datetime(y, mo, da, h, mi, s, tzinfo=datetime.timezone.utc).timestamp())


def _clean_old(art_dir: Path, bug_id: str) -> None:
    for old in [art_dir / "screenshots" / f"{bug_id}-replay.txt",
                art_dir / "screenshots" / f"{bug_id}.txt"]:
        old.unlink(missing_ok=True)


def run(out_root: Path, target: str, server_log: Path | None) -> dict:
    tree = out_root / "BugReport"
    run_id = None
    counts = {"verified": 0, "unverified": 0, "png": 0, "cast": 0, "log": 0, "unreachable": 0}
    offset = len(server_log.read_text(errors="replace")) if server_log and server_log.is_file() else 0

    bug_files = sorted(tree.glob("*/verified_bugs/BUG-*.json")) + \
        sorted((tree / "unverified").glob("*/*.json"))
    for bf in bug_files:
        if bf.stem.endswith(".md"):
            continue
        try:
            bug = json.loads(bf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        verified = "verified_bugs" in bf.parts
        run_id = run_id or bug.get("run_id") or bug.get("_source", {}).get("run_id")
        ts = _ts_from_run(run_id or "RUN-20260101-000000")
        if verified:
            agent = bf.parent.parent.name
            rel_prefix = agent
            art_dir = tree / agent
        else:
            category = bf.parent.name  # unverified/<category>/<ID>.json
            agent = bug.get("finding_agent") or "unknown"
            rel_prefix = f"unverified/{category}"
            art_dir = tree / "unverified" / category
        bug_id = bug.get("id") or bug.get("bug_id")

        attach, offset = CE.capture(bug, agent, rel_prefix, art_dir, target, ts, server_log, offset)
        _clean_old(art_dir, bug_id)

        has_log = "log" in attach
        if "screenshot" in attach:
            counts["png"] += 1
        if "recording" in attach:
            counts["cast"] += 1
        if has_log:
            counts["log"] += 1

        # rewrite attachments + completeness on the report
        if verified:
            bug["attachments"] = attach
            src = bug.setdefault("_source", {})
            comp = dict(src.get("artifact_completeness") or {})
            comp.update({"screenshot": "screenshot" in attach,
                         "recording": "recording" in attach, "logs": has_log})
            src["artifact_completeness"] = comp
            bf.write_text(json.dumps(bug, indent=2))
            (bf.with_suffix("")).with_suffix(".md").write_text(BD._bug_markdown(bug))
            counts["verified"] += 1
        else:
            arts = bug.setdefault("artifacts", {})
            arts["screenshot_path"] = attach.get("screenshot")
            arts["recording_path"] = attach.get("recording")
            arts["log_path"] = attach.get("log")
            comp = dict(bug.get("artifact_completeness") or {})
            comp.update({"screenshot": "screenshot" in attach,
                         "recording": "recording" in attach, "logs": has_log})
            bug["artifact_completeness"] = comp
            bf.write_text(json.dumps(bug, indent=2))
            counts["unverified"] += 1
    return counts


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: recapture_bug_evidence.py <out_root> <target> [server_log]", file=sys.stderr)
        sys.exit(2)
    out_root = Path(sys.argv[1]).resolve()
    target = sys.argv[2]
    server_log = Path(sys.argv[3]).resolve() if len(sys.argv) > 3 else None
    counts = run(out_root, target, server_log)
    print("RECAPTURE:", json.dumps(counts))


if __name__ == "__main__":
    main()

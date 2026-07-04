#!/usr/bin/env python3
"""Nested-aware run-output regenerator (flat->nested orchestration fix).

The foundry migrated agents/judge/results from flat (<name>) to nested
(<group>/<name>), but the per-agent phase4_*.sh scripts, _generate_dispatches.py,
and judge_score invocations still use flat, inconsistent, BARE-leaderboard paths.
Rather than edit 44 stale scripts, this ONE driver regenerates every judged
agent's run output at the correct nested, timestamped path that verify_build
--phase 6 expects: results/<group>/<name>/leaderboard-<TS>.json (+ .md), plus a
valid results/runs/<RID>/ receipt set.

Per agent:
  1. locate its lane runner in scripts/ (naming varies; matched by the agent
     name or its group-prefixed name after '__', or the generic run_agents.py).
  2. run the lane runner (backend = claude-cli shim) -> writes receipts to a
     fresh results/runs/<RID>/.
  3. run judge/<group>/<name>/score.py --run-id <RID>.
  4. run scripts/judge_score.py with --metric judge/<group>/<name>/metric.json
     and --out-prefix results/<group>/<name>/leaderboard-<TS> (timestamped).

Resumable: an agent that already has a timestamped leaderboard is skipped unless
--force. create-postman-collection is skipped (out of scope, relocating).

Usage:
  python scripts/regen_outputs.py [--only <name>] [--force] [--list]
"""
from __future__ import annotations

import argparse
import glob
import json
import os
import signal
import subprocess
import sys
from pathlib import Path

# Per-runner wall-clock cap. The `claude -p` shim is slow and one lagging framework
# can stall the whole batch; on timeout the runner's process group is killed and any
# partial run dir it already wrote is still scored (a partial leaderboard satisfies
# phase-6's "has a leaderboard" check; the update flow re-judges properly later).
RUNNER_TIMEOUT_S = int(os.environ.get("REGEN_RUNNER_TIMEOUT", "600"))

WS = Path(__file__).resolve().parents[1]
PY = str(WS / ".venv" / "bin" / "python") if (WS / ".venv" / "bin" / "python").exists() else sys.executable
SKIP = {"create-postman-collection"}  # out of scope (relocating to general/)
# Groups to skip. Code review is skipped for the api-tester update batch (user
# directive), so the ~19 code-review reviewer agents need neither a rebuilt
# leaderboard nor a run — set REGEN_SKIP_GROUPS="" to include them.
SKIP_GROUPS = set(filter(None, os.environ.get("REGEN_SKIP_GROUPS", "code-review").split(",")))


def judged_agents() -> list[tuple[str, str]]:
    """Every (group, name) with a judge score.py, sorted, minus SKIP / SKIP_GROUPS."""
    out = []
    for sc in sorted(glob.glob(str(WS / "judge" / "*" / "*" / "score.py"))):
        p = Path(sc)
        name, group = p.parent.name, p.parent.parent.name
        if name not in SKIP and group not in SKIP_GROUPS:
            out.append((group, name))
    return out


def find_runner(group: str, name: str) -> Path | None:
    """Locate the lane runner for one agent. Naming varies across the foundry:
    run_<x>_agents__<name>.py, run_<x>_agents__<group>-<name>.py,
    run_agents_<x>__<name>.py, etc. Match on the '__<suffix>.py' tail equal to
    the agent name or its group-prefixed name. Fall back to the generic runner."""
    candidates = [name, f"{group}-{name}"]
    for scr in glob.glob(str(WS / "scripts" / "run_*.py")):
        tail = Path(scr).stem.split("__", 1)
        if len(tail) == 2 and tail[1] in candidates:
            return Path(scr)
    # The generic run_agents.py is hardwired to validate-request-payloads (the
    # "current task"); it is NOT parameterizable, so it is a valid runner ONLY for
    # that agent. Every other agent that reaches here has no dedicated runner.
    generic = WS / "scripts" / "run_agents.py"
    if name == "validate-request-payloads" and generic.is_file():
        return generic
    return None


def run_dirs() -> set[str]:
    return set(glob.glob(str(WS / "results" / "runs" / "*")))


def run_frameworks_direct(group: str, name: str, timeout: int) -> str | None:
    """Fallback for an agent with no dedicated lane runner: run its four nested
    framework run.py directly under one shared run-id (mirrors run_agents._launch),
    so each writes its receipt to results/runs/<RID>/. Returns the RID, or None if
    no framework emitted. The subagent receipt is named '<group>-<name>' per the
    foundry's AGENT-string convention; the other three keep their framework name."""
    import uuid
    # Date.now()/uuid are fine here (this is not a resumable workflow script).
    rid = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
    run_dir = WS / "results" / "runs" / rid
    run_dir.mkdir(parents=True, exist_ok=True)
    fw_agent = {"langgraph": "langgraph", "crewai": "crewai",
                "claude_sdk": "claude_sdk", "subagent": f"{group}-{name}"}
    emitted = False
    for fw, agent_str in fw_agent.items():
        rp = WS / "agents" / group / name / fw / "run.py"
        if not rp.is_file():
            continue
        env = dict(os.environ)
        env["FORGE_PROVIDER"] = env.get("FORGE_PROVIDER", "claude-cli")
        env["PATH"] = f"{WS / '.venv' / 'bin'}:{env.get('PATH','')}"
        env["FORGE_WORKSPACE"] = str(WS)
        env["FORGE_RUN_ID"] = rid
        env["FORGE_AGENT"] = agent_str
        env["FORGE_SANDBOX_ROOT"] = str(WS)
        try:
            p = subprocess.Popen([PY, str(rp)], cwd=str(WS), env=env, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                 start_new_session=True)
            p.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(os.getpgid(p.pid), signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
            p.communicate()
        if (run_dir / f"{agent_str}.json").exists():
            emitted = True
    return rid if emitted else None


def run(cmd: list[str], timeout: int | None = None) -> tuple[int, str]:
    env = dict(os.environ)
    env["FORGE_PROVIDER"] = env.get("FORGE_PROVIDER", "claude-cli")
    env["PATH"] = f"{WS / '.venv' / 'bin'}:{env.get('PATH','')}"
    # start_new_session so we can kill the whole process group (the runner spawns 4
    # framework subprocesses) on timeout rather than orphaning them.
    proc = subprocess.Popen(cmd, cwd=str(WS), env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            start_new_session=True)
    try:
        out, _ = proc.communicate(timeout=timeout)
        return proc.returncode, out or ""
    except subprocess.TimeoutExpired:
        try:
            os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
        except (ProcessLookupError, PermissionError):
            pass
        out, _ = proc.communicate()
        return 124, (out or "") + f"\n[regen] runner killed after {timeout}s timeout"


def has_leaderboard(group: str, name: str) -> bool:
    return bool(glob.glob(str(WS / "results" / group / name / f"leaderboard-*.json")))


def regen_one(group: str, name: str, force: bool) -> dict:
    tag = f"{group}/{name}"
    if has_leaderboard(group, name) and not force:
        return {"agent": tag, "status": "skip (leaderboard exists)"}
    runner = find_runner(group, name)
    if runner is None:
        # No dedicated lane runner: run the four framework run.py directly.
        rid = run_frameworks_direct(group, name, RUNNER_TIMEOUT_S)
        if rid is None:
            return {"agent": tag, "status": "FAIL: no lane runner and direct frameworks emitted nothing"}
    else:
        before = run_dirs()
        rc, out = run([PY, str(runner), "--workspace", "."], timeout=RUNNER_TIMEOUT_S)
        new = sorted(run_dirs() - before, key=os.path.getmtime)
        if not new:
            # No fresh run dir means the runner produced no receipts (crashed / emitted
            # nothing). Never score a stale run dir as if it were this agent's.
            return {"agent": tag, "status": f"FAIL: runner rc={rc}, no new run dir", "log": out[-800:]}
        rid = Path(new[-1]).name
    ts = rid.split("-", 1)[0]

    score = WS / "judge" / group / name / "score.py"
    metric = WS / "judge" / group / name / "metric.json"
    rc2, out2 = run([PY, str(score), "--workspace", ".", "--run-id", rid])
    if rc2 != 0:
        return {"agent": tag, "status": f"FAIL: score.py rc={rc2}", "rid": rid, "log": out2[-800:]}

    prefix = f"results/{group}/{name}/leaderboard-{ts}"
    cmd = [PY, str(WS / "scripts" / "judge_score.py"), "--workspace", ".", "--run-id", rid]
    if metric.is_file():
        cmd += ["--metric", f"judge/{group}/{name}/metric.json"]
    cmd += ["--out-prefix", prefix]
    rc3, out3 = run(cmd)
    if rc3 != 0 or not has_leaderboard(group, name):
        return {"agent": tag, "status": f"FAIL: judge_score rc={rc3}", "rid": rid, "log": out3[-600:]}
    # remove any bare leaderboard.json a stale step may have dropped
    for bare in ("leaderboard.json", "leaderboard.md"):
        b = WS / "results" / group / name / bare
        if b.exists():
            b.unlink()
    return {"agent": tag, "status": "ok", "rid": rid}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--list", action="store_true")
    args = ap.parse_args()

    agents = judged_agents()
    if args.only:
        agents = [(g, n) for g, n in agents if n == args.only or f"{g}/{n}" == args.only]
    if args.list:
        for g, n in agents:
            r = find_runner(g, n)
            print(f"{'HAS-LB' if has_leaderboard(g, n) else 'no-lb ':7} {g}/{n:45} runner={r.name if r else 'NONE'}")
        print(f"\n{len(agents)} judged agents")
        return 0

    results = []
    for i, (g, n) in enumerate(agents, 1):
        print(f"[{i}/{len(agents)}] {g}/{n} ...", flush=True)
        res = regen_one(g, n, args.force)
        results.append(res)
        print(f"    -> {res['status']}" + (f"  ({res.get('rid','')})" if res.get("rid") else ""), flush=True)
        if res["status"].startswith("FAIL"):
            print("    LOG:", res.get("log", "")[-400:], flush=True)

    ok = [r for r in results if r["status"] == "ok"]
    skip = [r for r in results if r["status"].startswith("skip")]
    fail = [r for r in results if r["status"].startswith("FAIL")]
    print(f"\n=== regen summary: ok={len(ok)} skip={len(skip)} FAIL={len(fail)} ===")
    for r in fail:
        print(f"  FAIL {r['agent']}: {r['status']}")
    (WS / "workspace").mkdir(exist_ok=True)
    (WS / "workspace" / "regen-summary.json").write_text(json.dumps(results, indent=2))
    return 1 if fail else 0


if __name__ == "__main__":
    sys.exit(main())

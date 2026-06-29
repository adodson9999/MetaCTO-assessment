"""Shared, deterministic plumbing for the four test-case-creator agents (n600).

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - read the build manifest (data/test-case-creator/manifest.json), filter enabled=true
  - for each enabled agent read its spec_path, slice out the How section + Metric line,
    and build the compact per-agent brief handed to the agent
  - run whatever per-agent object array the agent emitted through the shared comparator
    vs the deterministic gold registry (agents/common/testcase_spec.build_*)
  - write the n600 DELIVERABLE — the deterministic, gap-free registry + summary (+ gaps
    file only if a discrepancy exists) — to results/test-case-registry*.json, and assert
    the registry count equals the total steps extracted
  - record per-framework reproduction accuracy under results/runs/<run>/<agent>/ and
    emit the headline metric for the judge
  - best-effort write a breadcrumb to the shared EverOS memory pool

Division of labour (mirrors the rest of the foundry): the LLM does the cognitive core
— turning ONE agent's How section into its step objects — injected as
`generate(cfg) -> list[object]`. The deterministic manifest read, gold computation,
registry/summary/gaps write, and the count assertion are this harness's job.

Fully air-gapped: no network target. DummyJSON is irrelevant to this task and is never
contacted or modified.
"""
from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
MANIFEST_PATH = Path(os.environ.get(
    "FORGE_TESTCASE_MANIFEST",
    WORKSPACE / "data" / "test-case-creator" / "manifest.json")).resolve()
RESULTS = WORKSPACE / "results"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import testcase_spec as tcspec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox guard
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


# --------------------------------------------------------------------------- #
# Manifest loading + briefing
# --------------------------------------------------------------------------- #
def _resolve_spec_path(spec_path: str) -> Path:
    """spec_path may be workspace-relative or manifest-dir-relative."""
    raw = Path(spec_path)
    if raw.is_absolute():
        return raw
    for base in (WORKSPACE, MANIFEST_PATH.parent):
        cand = (base / raw).resolve()
        if cand.exists():
            return cand
    return (WORKSPACE / raw).resolve()


def load_manifest() -> list[dict]:
    data = json.loads(MANIFEST_PATH.read_text())
    if not isinstance(data, list):
        raise ValueError("manifest.json must be a JSON array of agent objects")
    return data


def agent_cfgs() -> list[dict]:
    """Enabled agents only, each carrying its name, full spec text, How section,
    and Metric line. Optionally narrowed by FORGE_ONLY_AGENTS (comma-separated names)."""
    out: list[dict] = []
    for entry in load_manifest():
        if not (isinstance(entry, dict) and entry.get("enabled") is True):
            continue
        spec_file = _resolve_spec_path(entry["spec_path"])
        _assert_sandbox(spec_file)
        spec_text = spec_file.read_text()
        how_text = tcspec.extract_how(spec_text) or ""
        metric_line = _metric_line(spec_text)
        out.append({
            "name": entry["name"],
            "spec_path": str(spec_file),
            "spec_text": spec_text,
            "how_text": how_text,
            "metric_line": metric_line,
        })
    only = os.environ.get("FORGE_ONLY_AGENTS", "").strip()
    if only:
        wanted = {x.strip() for x in only.split(",") if x.strip()}
        out = [c for c in out if c["name"] in wanted]
    # D1: CI scoping — when FORGE_TESTCASE_AGENT is set, return only that agent's config.
    # The env var value must match cfg["name"] exactly
    # (e.g. "api-tester-validate-request-payloads").
    target = os.environ.get("FORGE_TESTCASE_AGENT", "").strip()
    if target:
        out = [c for c in out if c["name"] == target]
    return out


def _metric_line(spec_text: str) -> str:
    for line in spec_text.splitlines():
        if line.lstrip().startswith(tcspec.METRIC_MARKER):
            return line.strip()
    return ""


def agent_brief(cfg: dict) -> str:
    """Compact, unambiguous per-agent brief handed to the LLM.

    If cfg contains 'retry_prefix' (str), it is prepended to the brief.
    retry_prefix is injected by run_testcase_test() on retry attempts 2 and 3
    to enforce JSON array output format. It is never present on attempt 1.
    """
    parts = [
        f"agent_name: {cfg['name']}",
        "how_text: |",
        *[f"  {line}" for line in cfg["how_text"].splitlines()],
        f"metric_line: {cfg['metric_line']}",
    ]
    brief = "\n".join(parts)
    # staging_prefix carries actual observations from the G1 harness run (set by D3).
    # retry_prefix is injected on attempt 2 and 3 to enforce JSON format (set by B2).
    # Order in the prompt: staging context first, then format correction, then the brief.
    staging_prefix = cfg.get("staging_prefix", "")
    retry_prefix   = cfg.get("retry_prefix", "")
    combined = "\n\n".join(p for p in [staging_prefix, retry_prefix] if p)
    return f"{combined}\n\n{brief}" if combined else brief


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# Deterministic n600 deliverable (gold registry; gap-free by construction)
# --------------------------------------------------------------------------- #
def write_deliverable(cfgs: list[dict]) -> dict:
    """Write the authoritative, deterministic registry the downstream n601 consumes.

    This is NOT an LLM artifact: it is the gold extraction, so it is gap-free and the
    count assertion always holds. Returns the gold bundle (registry + summary)."""
    gold = tcspec.build_reference_registry(
        [{"name": c["name"], "spec_text": c["spec_text"]} for c in cfgs])
    registry, summary = gold["registry"], dict(gold["summary"])
    summary["timestamp"] = datetime.now(timezone.utc).isoformat()

    RESULTS.mkdir(parents=True, exist_ok=True)
    reg_path = RESULTS / "test-case-registry.json"
    sum_path = RESULTS / "test-case-registry-summary.json"
    gap_path = RESULTS / "test-case-registry-gaps.json"
    for p in (reg_path, sum_path, gap_path):
        _assert_sandbox(p)

    reg_path.write_text(json.dumps(registry, indent=2))
    sum_path.write_text(json.dumps(summary, indent=2))

    # Count assertion (step 10): registry length must equal total steps extracted.
    if summary["gaps_found"]:
        gaps = [{"agent": a, "step_id": None, "reason": "parse_error"}
                for a in gold["parse_error_agents"]]
        gap_path.write_text(json.dumps(gaps, indent=2))
    elif gap_path.exists():
        gap_path.unlink()  # stale gaps from a prior incomplete run

    assert summary["total_test_cases_created"] == summary["total_steps_extracted"] \
        or summary["gaps_found"], "registry count vs steps mismatch with no gaps recorded"
    return gold


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_testcase_test(agent: str, generate) -> dict:
    """Drive the whole task for one framework agent.

    generate(cfg: dict) -> the JSON array of test-case objects for that ONE agent spec.
    The harness aggregates the framework's emitted objects, scores them against the gold
    registry, and (once) writes the deterministic n600 deliverable. generate may raise;
    recorded per agent.
    """
    # D3a: Import staging module if available. Failures are silently suppressed —
    # the staging brief is optional evidence; test-case-creator works without it.
    _staging_mod = None
    try:
        import sys as _sys
        _sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
        import staging as _staging_mod  # type: ignore[import]
    except Exception:  # noqa: BLE001
        pass

    cfgs = agent_cfgs()

    # The deterministic, gap-free deliverable consumed by n601 (written every run; idempotent).
    gold = write_deliverable(cfgs)

    emitted_registry: list[dict] = []
    per_agent = []
    _RETRY_PREFIXES = [
        "",   # attempt 1: no prefix
        (
            "CRITICAL: Your previous response was not a valid JSON array. "
            "Output ONLY a JSON array. Start with [ and end with ]. "
            "No other text, no markdown fences, no explanation."
        ),
        (
            "MANDATORY FORMAT — your response must be exactly this structure:\n"
            '[{"tc_id":"TC-1","agent":"<agent_name>","description":"...","steps":[...]}]\n'
            "Output ONLY the JSON array. Nothing else."
        ),
    ]
    MAX_ATTEMPTS = 3

    for cfg in cfgs:
        cases: list = []
        gen_error: str | None = None

        # D3b: Load staged findings for this agent and inject as staging_prefix.
        # staging_brief() returns "" if no staging files exist for this agent.
        if _staging_mod is not None:
            try:
                _stage_text = _staging_mod.staging_brief(cfg["name"])
                if _stage_text:
                    cfg = dict(cfg, staging_prefix=_stage_text)
            except Exception:  # noqa: BLE001
                pass

        for attempt in range(MAX_ATTEMPTS):
            attempt_cfg = dict(cfg)
            if attempt > 0:
                attempt_cfg["retry_prefix"] = _RETRY_PREFIXES[attempt]

            try:
                result = generate(attempt_cfg) or []
                if not isinstance(result, list):
                    result = []
            except Exception as e:  # noqa
                gen_error = f"{type(e).__name__}: {e}"
                break  # exception is unrecoverable for this cfg; do not retry

            if result:
                cases = result
                gen_error = None
                break

            gen_error = f"empty output on attempt {attempt + 1} of {MAX_ATTEMPTS}"

        if not cases:
            sentinel = {
                "tc_id": f"TC-ERR-{cfg['name']}",
                "agent": cfg["name"],
                "run_id": RUN_ID,
                "outcome": "ERROR",
                "error": (
                    gen_error or
                    f"test-case-creator returned empty/unparseable output "
                    f"after {MAX_ATTEMPTS} attempts"
                ),
                "pass": False,
                "fail": False,
            }
            emitted_registry.append(sentinel)

        emitted_registry.extend([c for c in cases if isinstance(c, dict)])
        per_agent.append({
            "agent_spec": cfg["name"],
            "emitted_count": len(cases),
            "attempts": attempt + 1,
            "error": gen_error,
        })

    scored = tcspec.score_registry(emitted_registry, gold["registry"])
    coverage = scored["coverage_rate_pct"]

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "test_case_coverage_rate_pct": coverage,
        "test_case_field_accuracy_pct": scored["field_accuracy_pct"],
        "gold_tc": scored["gold_tc"], "present_tc": scored["present_tc"],
        "emitted_tc": len(emitted_registry),
        "missing_tc": scored["missing_tc"],
        "field_mismatches": scored["field_mismatches"],
        "per_agent_spec": per_agent,
        "deliverable_summary": gold["summary"],
    }
    run_dir = RESULTS / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))
    (run_dir / f"{agent}.emitted-registry.json").write_text(
        json.dumps(sorted(emitted_registry, key=lambda c: str(c.get("tc_id"))), indent=2))

    emit(agent, coverage, str(cases_path), extra={
        "test_case_coverage_rate_pct": coverage,
        "test_case_field_accuracy_pct": scored["field_accuracy_pct"],
        "gold_tc": scored["gold_tc"]})

    everos_note(agent, f"test-case-creator run: coverage={coverage}% "
                       f"field_accuracy={scored['field_accuracy_pct']}% "
                       f"({scored['present_tc']}/{scored['gold_tc']} gold cases)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/test-case-creator/<agent>.json. metric_value is the
    framework's coverage of the gold registry; the judge later confirms it."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-case-creator" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = RESULTS / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "test_case_coverage_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json_array(text: str):
    """Pull the first balanced JSON array out of arbitrary LLM text."""
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("[")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "[":
                depth += 1
            elif text[i] == "]":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, list) else None
    except Exception:  # noqa
        return None

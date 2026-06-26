"""Shared, deterministic plumbing for the four create-postman-collection agents ("n601").

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is the
identical substrate every framework sits on, so leaderboard differences are attributable
to the framework + its gated prompt + its evolved skill — never to divergent plumbing. In
particular, the registry->collection transform itself lives here (read the registry, gap
pre-check, filter involves_http_call, build one item per HTTP test case, group into
per-agent folders, assemble + read back + recursively count, write gaps/summary, run
Newman), so all four agents exercise n601 the exact same way; what differs is only the
CONTRACT each agent emitted (the regexes / triggers / variables / group key it must
reproduce).

n601 makes NO HTTP calls of its own and NEVER touches DummyJSON — it is a pure transform
over JSON files in the workspace.

The framework-specific part — turning the brief into the Postman Generation Contract via
the backend LLM — is injected as `generate(cfg) -> contract dict`.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
SPEC_PATH = WORKSPACE / "data" / "create-postman-collection" / "postman_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import postman_spec  # noqa: E402

# Fixed UUID/date for in-harness builds so per-agent collections are reproducible; the
# production CLI uses a real runtime uuid4 + ISO date (n601 step 8).
HARNESS_UUID = "00000000-0000-4000-8000-0000000006a1"
HARNESS_DATE = os.environ.get("FORGE_POSTMAN_DATE", "2026-06-26")


# --------------------------------------------------------------------------- #
# Sandbox guard
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


# --------------------------------------------------------------------------- #
# Spec loading + registry seeding + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    # held-out override (evolution gate only): swap in a different registry fixture so a
    # candidate skill is validated on a registry it was NOT tuned on.
    ho_reg = os.environ.get("FORGE_HELDOUT_REGISTRY")
    if ho_reg:
        spec["registry_fixture"] = ho_reg
    ho_sum = os.environ.get("FORGE_HELDOUT_SUMMARY")
    if ho_sum:
        spec["summary_fixture"] = ho_sum
    return spec


def run_cfg() -> dict:
    return load_spec()


def load_registry(cfg: dict) -> tuple[list, dict]:
    """The forge harness reads the n600-style input from the FIXTURE files directly
    (data/create-postman-collection/), NOT from the shared results/test-case-registry.json.
    This keeps the four-agent measurement deterministic and isolated from the sibling n600
    build, which writes the real results/test-case-registry.json concurrently. The
    production CLI (scripts/postman_collection_cli.py) is the path that consumes the real
    results/ registry. FORGE_HELDOUT_REGISTRY/SUMMARY swap in a held-out fixture for the
    evolution gate."""
    registry = json.loads((WORKSPACE / cfg["registry_fixture"]).read_text())
    summary = json.loads((WORKSPACE / cfg["summary_fixture"]).read_text())
    return (registry if isinstance(registry, list) else []), summary


def brief(cfg: dict) -> str:
    """Compact, unambiguous n601 contract spec handed to the LLM. The agent must emit a
    Postman Generation Contract reproducing exactly these knobs."""
    return "\n".join([
        f"registry_path: {cfg['registry_path']}   # JSON array of test cases; each has tc_id, agent, step_text, involves_http_call",
        f"filter_field: {cfg['filter_field']}   # keep only test cases where this field is true",
        f"group_by: {cfg['group_by']}   # group the built items into one folder per distinct value of this field, in first-appearance order",
        f"base_url: {cfg['base_url']}   # the {{{{base_url}}}} collection variable value; every request url is {{{{base_url}}}} + the extracted path",
        f"collection_name_prefix: {cfg['collection_name_prefix']}   # collection info.name is this prefix + ' — ' + the ISO date",
        "method_pattern: \\b(GET|POST|PUT|DELETE|PATCH|HEAD)\\b  (first match; default GET)",
        "path_pattern: (\\/[\\w\\-\\.{}\\/]+)  (first match; default /unknown)",
        "body_triggers: 'with body' | 'with a valid body' | 'body:' | 'body =' -> body mode raw '{}' with options {\"raw\":{\"language\":\"json\"}}; else body mode none",
        "header_triggers (substring -> header, in this order): 'Authorization'->Authorization:{{auth_token}}; 'X-Correlation-ID'->X-Correlation-ID:{{corr_id}}; 'If-None-Match'->If-None-Match:{{etag_value}}; 'Content-Type: multipart'->Content-Type:multipart/form-data; 'Idempotency-Key'->Idempotency-Key:{{idempotency_key}}",
        "status_pattern_primary: (?:Assert(?:s)?\\s+(?:response\\s+)?(?:code\\s+)?(?:=|equals|is\\s+exactly|exactly)\\s*)([1-9][0-9]{2})",
        "status_pattern_fallback: →\\s+assert\\s+(?:exactly\\s*)?([1-9][0-9]{2})  (else expected status 0)",
        "variables: base_url, auth_token, corr_id, etag_value, idempotency_key (all type string; base_url value = base_url above, the rest empty)",
    ])


# --------------------------------------------------------------------------- #
# Collection assembly + verification (n601 steps 5-9)
# --------------------------------------------------------------------------- #
def assemble(registry: list, contract: dict, iso_date: str, postman_id: str) -> tuple[dict, list]:
    """Apply a contract to the registry. Returns (collection, http_tcs_built)."""
    http_tcs = postman_spec.filter_http(registry, contract)
    collection = postman_spec.build_collection(http_tcs, contract, iso_date, postman_id)
    return collection, http_tcs


def gaps_against(registry: list, collection: dict, cfg: dict) -> list:
    """MISSING_TC_IDS: canonical HTTP tc_ids absent as a request-item name (n601 step 9)."""
    ref = postman_spec.reference_contract(cfg)
    canonical = postman_spec.filter_http(registry, ref)
    names = {it.get("name") for it in postman_spec.collect_request_items(collection or {})}
    return [{"tc_id": tc.get("tc_id"), "agent": tc.get("agent")}
            for tc in canonical if tc.get("tc_id") not in names]


# --------------------------------------------------------------------------- #
# Newman dry-run + stdlib structural validation (n601 step 11)
# --------------------------------------------------------------------------- #
def newman_dry_run(collection_path: Path) -> tuple[bool | None, str]:
    """Validate the collection is structurally valid Postman v2.1 (n601 step 11).

    Returns (valid, detail): True/False after a real check, or None if Newman is not
    installed (recorded as a WARNING per the spec, never aborts).

    NOTE: Newman 6.x has no `--dry-run` flag (and `newman run` alone would fire every
    request at base_url, which is not a schema check). The faithful, request-free
    equivalent is to load the collection through `postman-collection` — the exact SDK
    Newman uses to parse a collection before running it (tools/newman/validate_collection.js).
    If the Collection constructs + round-trips, the file is valid v2.1.
    """
    isolated = WORKSPACE / "tools" / "newman"
    validator = isolated / "validate_collection.js"
    node = shutil.which("node")
    if not (validator.exists() and (isolated / "node_modules" / "postman-collection").exists()
            and node):
        return None, "newman-not-installed"
    try:
        proc = subprocess.run([node, str(validator), str(collection_path)],
                              capture_output=True, text=True, timeout=120)
    except Exception as e:  # noqa
        return None, f"newman-exec-error: {type(e).__name__}"
    if proc.returncode == 0:
        return True, f"postman-collection SDK validated v2.1 ({proc.stdout.strip()} request items)"
    if proc.returncode == 2:
        return None, "newman-validator-usage-error"
    return False, (proc.stderr or proc.stdout or "non-zero exit").strip()[-400:]


def structural_valid(collection: dict) -> tuple[bool, list]:
    """Stdlib check of Postman v2.1 essentials — a validity signal even without Newman."""
    errs: list = []
    if not isinstance(collection, dict):
        return False, ["collection is not an object"]
    info = collection.get("info")
    if not isinstance(info, dict) or not info.get("name") or not info.get("schema"):
        errs.append("info.name/info.schema missing")
    if not isinstance(collection.get("item"), list):
        errs.append("top-level item is not an array")
    for it in postman_spec.collect_request_items(collection):
        req = it.get("request")
        if not isinstance(req, dict) or not req.get("method") or "url" not in req:
            errs.append(f"item {it.get('name')!r} has a malformed request")
            break
    return (not errs), errs


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _everos_config()
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


def _everos_config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_postman_test(agent: str, generate) -> dict:
    """Drive the whole n601 task for one agent.

    generate(cfg: dict) -> the Postman Generation Contract (a dict of the knobs in
        postman_spec.reference_contract). The harness applies it to the registry, builds
        the collection, reads it back, recursively counts request items, computes gaps,
        runs Newman, and scores every scenario. Whatever the agent's contract gets wrong
        diverges from gold on the relevant token. generate may raise; recorded.
    """
    cfg = run_cfg()
    registry, summary = load_registry(cfg)

    try:
        contract = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        contract, gen_error = {}, f"{type(e).__name__}: {e}"
    if not isinstance(contract, dict) or not contract:
        # An empty/failed contract still gets graded (every knob 'missing' -> low fidelity).
        contract = contract if isinstance(contract, dict) else {}

    # Build the per-agent collection (results/runs/<run>/<agent>.postman-collection.json so
    # the four parallel agents never clobber each other or the canonical CLI output).
    collection, _ = assemble(registry, contract, HARNESS_DATE, HARNESS_UUID)
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    coll_path = run_dir / f"{agent}.postman-collection.json"
    _assert_sandbox(coll_path)
    coll_path.write_text(json.dumps(collection, indent=2))

    # Read it back + recursive walk (n601 step 9)
    reloaded = json.loads(coll_path.read_text())
    item_count = postman_spec.recursive_item_count(reloaded)
    ref = postman_spec.reference_contract(cfg)
    http_tc_count = len(postman_spec.filter_http(registry, ref))
    rate = postman_spec.coverage_rate(item_count, http_tc_count)
    missing = gaps_against(registry, reloaded, cfg)

    # Validation (n601 step 11): structural always; Newman best-effort.
    struct_ok, struct_errs = structural_valid(reloaded)
    newman_valid, newman_detail = newman_dry_run(coll_path)

    # Score scenarios vs ideal
    observed = postman_spec.evaluate(reloaded, registry, summary, cfg)
    ideal = postman_spec.ideal_for(registry, cfg)
    scenarios = []
    total = correct = 0
    for label in postman_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = postman_spec.correct(label, tok, ideal)
        scenarios.append({"scenario": label, "ideal": ideal[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "postman_coverage_rate_pct": rate,
        "http_tc_count": http_tc_count, "postman_item_count": item_count,
        "gap_count": http_tc_count - item_count, "missing_tc_ids": missing,
        "agents_covered": int(observed.get("agents_covered", "0") or 0),
        "newman_valid": newman_valid, "newman_detail": newman_detail,
        "structural_valid": struct_ok, "structural_errors": struct_errs,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "emitted_contract": contract, "error": gen_error,
        "collection_path": str(coll_path),
        "scenarios": scenarios,
    }
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "postman_coverage_rate_pct": rate,
        "postman_item_count": item_count,
        "http_tc_count": http_tc_count,
        "scenarios_api_correct": correct,
        "newman_valid": newman_valid})

    everos_note(agent, f"create-postman-collection run: coverage_rate={rate}% "
                       f"(items={item_count}/{http_tc_count}, scenarios_ok={correct}/{total}, "
                       f"newman={newman_valid})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline Postman
    Coverage Rate; the judge later overwrites metric_value with fidelity-to-gold for
    ranking."""
    metric = {}
    mp = WORKSPACE / "judge" / "create-postman-collection" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "postman_coverage_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
    import re
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # noqa
        return None

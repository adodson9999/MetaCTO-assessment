"""Shared, deterministic driver for the four code-review-minimalist agents (group
code-review, short name minimalist).

NOT agent instruction (carries no debate-gated prompt lines). The identical substrate every
framework sits on. Responsibilities (all deterministic, no LLM):
  - load the labeled held-out cases (held_out.jsonl)
  - for each case: build the per-case brief (the code to rate), hand it to the injected
    generate(), capture the emitted {rating, notes} decision
  - materialise a per-case review artifact, score the emitted decision (1.0 iff the strict
    {rating, notes} schema passes AND the rating is within the case's gold band)
  - emit results/runs/<run>/<agent>.json + <agent>.cases.json and a best-effort EverOS note

The framework-specific part — turning one code brief into the {rating, notes} decision via
the backend LLM — is injected as generate(brief) -> decision dict.
"""
from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TASK_DIR = "code-review-minimalist"
SPEC_PATH = WORKSPACE / "data" / TASK_DIR / "codereview_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import codereview_spec  # noqa: E402


def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    ho = os.environ.get("FORGE_HELDOUT_FIXTURE")  # evolution gate only
    if ho:
        spec["held_out_path"] = ho
    return spec


def run_cfg() -> dict:
    return load_spec()


def _review_one_case(case: dict, generate, out_dir: Path) -> tuple[dict, float, str | None]:
    """Run one labeled case through the agent and score it. Returns (review, elapsed,
    gen_error). A raising or empty generate yields an empty decision (which scores 0)."""
    cid = case["id"]
    the_brief = codereview_spec.brief(case)

    t0 = time.monotonic()
    try:
        decision, gen_error = generate(the_brief) or {}, None
    except Exception as e:  # noqa
        decision, gen_error = {}, f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0

    cells = codereview_spec.score_decision(decision, case["gold_band"])
    review = {
        "case_id": cid, "run_id": RUN_ID,
        "gold_band": list(case["gold_band"]),
        "emitted": decision,
        "schema_ok": cells["schema_ok"],
        "band_hit": cells["band_hit"],
        "case_score": cells["case_score"],
        "gen_error": gen_error,
    }
    rp = out_dir / f"{cid}.json"
    _assert_sandbox(rp)
    rp.write_text(json.dumps(review, indent=2))
    return review, elapsed, gen_error


def run_codereview_test(agent: str, generate) -> dict:
    """Drive the whole minimalist task for one agent: score every labeled case's emitted
    {rating, notes} (strict schema + in-band) and record rating_band_accuracy = the mean
    case_score. generate(brief) -> the {rating, notes} dict; may raise (scored as empty)."""
    spec = run_cfg()
    cases = codereview_spec.load_cases(spec["held_out_path"])

    out_dir = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.reviews"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases_out, gen_errors = [], []
    score_total = 0.0
    schema_ok_count = 0
    elapsed_total = 0.0
    for case in cases:
        review, elapsed, gen_error = _review_one_case(case, generate, out_dir)
        elapsed_total += elapsed
        score_total += review["case_score"]
        schema_ok_count += 1 if review["schema_ok"] else 0
        if gen_error:
            gen_errors.append({"case": case["id"], "error": gen_error})
        cases_out.append(review)

    total = len(cases_out)
    band_accuracy = round(score_total / total, 4) if total else 0.0
    schema_valid_pct = round(100.0 * schema_ok_count / total, 2) if total else 0.0

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "rating_band_accuracy": band_accuracy,
        "cases_total": total,
        "schema_valid_pct": schema_valid_pct,
        "elapsed_seconds": round(elapsed_total, 3),
        "tokens": {"total_tokens": int(os.environ.get("FORGE_LAST_TOKENS", "0") or 0)},
        "gen_errors": gen_errors,
        "cases": cases_out,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, band_accuracy, str(cases_path), extra={
        "rating_band_accuracy": band_accuracy,
        "schema_valid_pct": schema_valid_pct,
        "cases_total": total})

    everos_note(agent, f"code-review-minimalist run: rating_band_accuracy={band_accuracy} "
                       f"over {total} cases; schema_valid={schema_valid_pct}%")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    metric = {}
    mp = WORKSPACE / "judge" / "code-review" / "minimalist" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "rating_band_accuracy"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def everos_note(agent: str, text: str) -> None:
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


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

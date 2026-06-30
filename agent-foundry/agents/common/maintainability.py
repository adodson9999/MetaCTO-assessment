"""Shared, deterministic driver for the four Maintainability code-review agents
(group ``code-review``, short name ``maintainability``).

NOT agent instruction (carries no debate-gated prompt lines). The identical substrate every
framework sits on. Responsibilities (all deterministic, no LLM):
  - load the held-out set (every ``{input_code, gold_band}`` case)
  - for each case: build the per-case brief, hand it to the injected ``generate()``, capture
    the emitted ``{rating, notes}`` object
  - score the emission vs the case's gold band (schema gate + in-band check = the metric)
  - emit ``results/runs/<run>/<agent>.json`` + ``<agent>.cases.json`` and a best-effort
    EverOS note

The framework-specific part — turning one code brief into the ``{rating, notes}`` object via
the backend LLM — is injected as ``generate(brief) -> decision dict``.
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
GROUP = "code-review"
SHORT = "maintainability"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import maintainability_spec  # noqa: E402


def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _rate_one_case(case: dict, generate, out_dir: Path) -> tuple[dict, float, str | None]:
    """Run one held-out case through the agent and score it. Returns (review, elapsed,
    gen_error). A raising or empty generate yields an empty decision (which scores 0)."""
    cid = case["id"]
    the_brief = maintainability_spec.brief(case)

    t0 = time.monotonic()
    try:
        decision, gen_error = generate(the_brief) or {}, None
    except Exception as e:  # noqa: BLE001
        decision, gen_error = {}, f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0

    cells = maintainability_spec.score_output(decision, case["gold_band"])
    review = {
        "case_id": cid, "run_id": RUN_ID,
        "gold_band": case["gold_band"],
        "emitted": decision,
        "schema_ok": cells["schema_ok"],
        "band_ok": cells["band_ok"],
        "score": cells["score"],
        "gen_error": gen_error,
    }
    rp = out_dir / f"{cid}.json"
    _assert_sandbox(rp)
    rp.write_text(json.dumps(review, indent=2))
    return review, elapsed, gen_error


def run_maintainability_test(agent: str, generate) -> dict:
    """Drive the whole maintainability task for one agent: score every held-out case's
    emitted ``{rating, notes}`` vs its gold band, write the per-case reviews + a cases file,
    record the metric. ``generate(brief) -> {rating, notes}``; may raise (scored as empty)."""
    cases = maintainability_spec.load_heldout(WORKSPACE)

    out_dir = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.reviews"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases_out, gen_errors = [], []
    score_sum = schema_ok_count = band_ok_count = 0.0
    elapsed_total = 0.0
    for case in cases:
        review, elapsed, gen_error = _rate_one_case(case, generate, out_dir)
        elapsed_total += elapsed
        score_sum += review["score"]
        schema_ok_count += 1 if review["schema_ok"] else 0
        band_ok_count += 1 if review["band_ok"] else 0
        if gen_error:
            gen_errors.append({"case": case["id"], "error": gen_error})
        cases_out.append(review)

    total = len(cases_out)
    metric_value = round(score_sum / total, 4) if total else 0.0
    schema_rate = round(100.0 * schema_ok_count / total, 2) if total else 0.0
    band_rate = round(100.0 * band_ok_count / total, 2) if total else 0.0

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "metric_name": "rating_band_accuracy",
        "rating_band_accuracy": metric_value,
        "cases_total": total,
        "schema_pass_pct": schema_rate,
        "band_pass_pct": band_rate,
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

    emit(agent, metric_value, str(cases_path), extra={
        "rating_band_accuracy": metric_value,
        "schema_pass_pct": schema_rate,
        "band_pass_pct": band_rate,
        "cases_total": total})

    everos_note(agent, f"maintainability run: rating_band_accuracy={metric_value} "
                       f"over {total} held-out cases; schema_pass={schema_rate}% "
                       f"band_pass={band_rate}%")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    metric = {}
    mp = WORKSPACE / "judge" / GROUP / SHORT / "metric.json"
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
    except Exception:  # noqa: BLE001
        return None

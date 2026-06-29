"""Shared, deterministic driver for the four Documentation-Reviewer agents ("n603").

NOT agent instruction (carries no debate-gated prompt lines). The identical substrate every
framework sits on. Responsibilities (all deterministic, no LLM):
  - load the spec + the full doc corpus (every file in cli/ and reference/)
  - for each labeled bug report: parse it, pre-grep candidate matches, build the per-case
    brief, hand it to the injected generate(), capture the emitted verdict decision
  - materialise a per-case review artifact, score the emitted decision vs the gold decision
    (verdict = the metric; source-of-truth file = the discriminator)
  - emit results/runs/<run>/<agent>.json + <agent>.cases.json and a best-effort EverOS note

The framework-specific part — turning one (bug report + corpus) brief into the verdict
decision via the backend LLM — is injected as generate(brief) -> decision dict.
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
TASK_DIR = "documentation-reviewer"
SPEC_PATH = WORKSPACE / "data" / TASK_DIR / "docreview_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import docreview_spec  # noqa: E402


def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    ho = os.environ.get("FORGE_HELDOUT_FIXTURE")  # evolution gate only
    if ho:
        spec["cases"] = json.loads((WORKSPACE / ho).read_text()).get("cases", spec["cases"])
    return spec


def run_cfg() -> dict:
    return load_spec()


def _rel(p) -> str | None:
    if p is None:
        return None
    try:
        return str(Path(p).resolve().relative_to(WORKSPACE))
    except Exception:  # noqa
        return str(p)


def _review_one_case(case: dict, corpus: list, gold: dict, max_passes: int,
                     generate, out_dir: Path) -> tuple[dict, float, str | None]:
    """Run one labeled case through the agent and score it. Returns (review, elapsed,
    gen_error). A raising or empty generate yields an empty decision (which scores 0)."""
    cid = case["id"]
    parsed = docreview_spec.parse_bug_report((WORKSPACE / case["report"]).read_text())
    candidates = docreview_spec.grep_corpus(corpus, case.get("disputed_keywords", []))
    the_brief = docreview_spec.brief(parsed, corpus, candidates, max_passes)

    t0 = time.monotonic()
    try:
        decision, gen_error = generate(the_brief) or {}, None
    except Exception as e:  # noqa
        decision, gen_error = {}, f"{type(e).__name__}: {e}"
    elapsed = time.monotonic() - t0

    gold_dec = gold.get(cid, {})
    cells = docreview_spec.score_decision(decision, gold_dec)
    review = {
        "case_id": cid, "run_id": RUN_ID, "report": case["report"],
        "emitted": decision, "gold_verdict": gold_dec.get("verdict"),
        "verdict_correct": cells["verdict"],
        "source_of_truth_file_correct": cells["source_of_truth_file"],
        "gen_error": gen_error,
    }
    rp = out_dir / f"{cid}.json"
    _assert_sandbox(rp)
    rp.write_text(json.dumps(review, indent=2))
    return review, elapsed, gen_error


def run_docreview_test(agent: str, generate) -> dict:
    """Drive the whole n603 task for one agent: score every labeled case's emitted verdict
    (and source-of-truth file) vs gold, write the per-case reviews + a cases file, record
    the metric. generate(brief) -> the six-key decision dict; may raise (scored as empty)."""
    spec = run_cfg()
    corpus = docreview_spec.load_corpus(spec)
    gold = docreview_spec.gold_index(WORKSPACE, TASK_DIR)
    max_passes = int(spec.get("max_search_passes", 3))

    out_dir = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.reviews"
    out_dir.mkdir(parents=True, exist_ok=True)

    cases_out, gen_errors = [], []
    verdict_correct = sot_correct = 0
    elapsed_total = 0.0
    for case in spec.get("cases", []):
        review, elapsed, gen_error = _review_one_case(
            case, corpus, gold, max_passes, generate, out_dir)
        elapsed_total += elapsed
        verdict_correct += 1 if review["verdict_correct"] else 0
        sot_correct += 1 if review["source_of_truth_file_correct"] else 0
        if gen_error:
            gen_errors.append({"case": case["id"], "error": gen_error})
        cases_out.append(review)

    verdict_total = len(cases_out)
    verdict_accuracy = round(100.0 * verdict_correct / verdict_total, 2) if verdict_total else 0.0
    sot_match = round(100.0 * sot_correct / verdict_total, 2) if verdict_total else 0.0

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "verdict_accuracy_pct": verdict_accuracy,
        "verdicts_total": verdict_total, "verdicts_correct": verdict_correct,
        "source_of_truth_match_pct": sot_match,
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

    emit(agent, verdict_accuracy, str(cases_path), extra={
        "verdict_accuracy_pct": verdict_accuracy,
        "source_of_truth_match_pct": sot_match,
        "verdicts_total": verdict_total})

    everos_note(agent, f"documentation-reviewer run: verdict_accuracy={verdict_accuracy}% "
                       f"over {verdict_total} reports; source-of-truth match={sot_match}%")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    metric = {}
    mp = WORKSPACE / "judge" / "general" / "documentation-reviewer" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "verdict_accuracy_pct"),
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

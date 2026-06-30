"""Deterministic substrate for the four code-review-api-contract agents (group code-review,
short name api-contract).

No debate-gated prompt lines live here (those are in apicontract_prompt.py). This module is
the identical, no-LLM plumbing every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill, never to divergent
plumbing. Responsibilities:

  - load the labeled held-out CASES (one JSON object per line of held_out.jsonl, each
    {"input_code": <str>, "gold_band": [lo, hi]}), assigning a stable, line-ordered id
  - assemble the per-case brief handed to the agent (the raw code to rate)
  - build the deterministic REFERENCE decision for a case (the oracle: midpoint of the
    gold band + a non-empty note) — used by the golden suite and the oracle self-test,
    never shown to the live agents
  - score an emitted decision: it scores 1.0 IFF it passes the strict {rating, notes}
    schema (exactly those two keys, rating an int 0-100, notes a non-empty string, one
    JSON object) AND rating falls inside the case's gold band, inclusive; else 0.0

The agent emits a {rating, notes} object as JSON only; it never reads or writes files,
never runs a subprocess, and never sends HTTP. The harness loads the cases and hands the
code to the agent as read-only data — the same split every other foundry agent uses.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()

# rating_band_accuracy is the scored field; there is no separate discriminator field
# (efficiency — tokens then elapsed — breaks ties in the judge).
DECISION_FIELDS = ("rating",)
REQUIRED_KEYS = frozenset({"rating", "notes"})
RATING_MIN, RATING_MAX = 0, 100


# --------------------------------------------------------------------------- #
# Case loading (the harness's job — the agent never touches the filesystem)
# --------------------------------------------------------------------------- #
def _case_id(index: int) -> str:
    return f"AC-{index:03d}"


def load_cases(held_out_path: str) -> list[dict]:
    """Every labeled held-out case, in file order.

    Returns a list of {"id", "input_code", "gold_band": (lo, hi)} records. Blank lines
    are skipped; ids are assigned by surviving-line order so the same file always yields
    the same ids (determinism)."""
    text = (WORKSPACE / held_out_path).read_text(encoding="utf-8")
    cases: list[dict] = []
    n = 0
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        obj = json.loads(line)
        lo, hi = obj["gold_band"]
        n += 1
        cases.append({"id": _case_id(n), "input_code": obj["input_code"],
                      "gold_band": (int(lo), int(hi))})
    return cases


def brief(case: dict) -> str:
    """The per-case input handed to the agent: the raw code to rate, verbatim."""
    return case["input_code"]


# --------------------------------------------------------------------------- #
# Reference oracle (golden suite + oracle self-test only; never shown to agents)
# --------------------------------------------------------------------------- #
def build_reference_decision(case: dict) -> dict:
    """The oracle: a deterministic correct decision for a case = the gold-band midpoint
    (an integer guaranteed inside the band) plus a non-empty note. An agent that lands in
    band with a valid schema scores 1.0; an empty/blank emission scores 0.0."""
    lo, hi = case["gold_band"]
    rating = (lo + hi) // 2
    note = ("no change needed" if rating >= RATING_MAX
            else "reference: version or restore the broken promise for affected callers "
                 "to reach 100")
    return {"rating": rating, "notes": note}


# --------------------------------------------------------------------------- #
# Scoring
# --------------------------------------------------------------------------- #
def _schema_ok(emitted: Any) -> bool:
    """Strict {rating, notes} contract: exactly those two keys, rating an int in
    [0, 100] (bool is rejected — bool is an int subclass), notes a non-empty string."""
    if not isinstance(emitted, dict):
        return False
    if set(emitted.keys()) != REQUIRED_KEYS:
        return False
    rating = emitted.get("rating")
    if isinstance(rating, bool) or not isinstance(rating, int):
        return False
    if not (RATING_MIN <= rating <= RATING_MAX):
        return False
    notes = emitted.get("notes")
    return isinstance(notes, str) and notes.strip() != ""


# Public alias so the golden runner and judge can call a stable name.
def schema_ok(emitted: Any) -> bool:
    return _schema_ok(emitted)


def score_decision(emitted: dict, gold_band: tuple[int, int]) -> dict:
    """Per-case correctness cells. case_score is 1.0 IFF the strict schema passes AND the
    rating is within the gold band inclusive, else 0.0. An empty or malformed emission
    yields schema_ok=False and case_score=0.0 (cannot saturate)."""
    ok = _schema_ok(emitted)
    lo, hi = gold_band
    band_hit = ok and lo <= int(emitted["rating"]) <= hi
    return {"schema_ok": ok, "band_hit": band_hit,
            "case_score": 1.0 if band_hit else 0.0}

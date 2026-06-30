#!/usr/bin/env python3
"""Generate the 10 candidate skill docs for the adversarial-input improvement tournament.

Each candidate is the debate-gated baseline (advinput_prompt.APPROVED_LINES) with ONE
bounded edit (insert / append a line), so every proposal is auditable and clears the same
"single-concern, deterministic-band language" bar the debate gate enforces. The proposing
agent (the orchestrator) derived these from the baseline judged run's per-case failures:
ALL FOUR frameworks rated the four crash-on-constructible-input cases (adv-003 missing-key,
adv-004 recursion, adv-005 decode, adv-006 no-limit) at exactly 70 — above their gold-band
ceilings (45/55/60/65) — while nailing the explicit ReDoS anchor (adv-002). The model
under-penalizes uncaught crashes, scoring them "weakness worth addressing" (70-89) instead
of "real problem/serious" (<=69). Edit C states the crash→band rule directly; Edit D adds
worked anchors for the exact missed shapes; Edit F adds a recursion anchor.

Output: candidates/round-01..round-10.md (round-00-baseline.md is written separately).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[3]
sys.path.insert(0, str(WS / "agents" / "common"))
import advinput_prompt as p  # noqa: E402

BASE = list(p.APPROVED_LINES)

# Edit C: an uncaught crash on a constructible input is never 70+. A new line inserted after
# the bands line (index 6).
CRASH_LINE = ("Code that crashes on a constructible malformed input — an unhandled KeyError, "
              "TypeError, IndexError, UnicodeDecodeError, RecursionError, OverflowError, or "
              "unbounded memory or CPU use — never rates in the 70 to 100 range; an uncaught "
              "crash is at most a real problem in the 40 to 69 band and is usually serious in "
              "the 1 to 39 band, and only code that rejects bad input cleanly, without "
              "crashing or hanging, earns 70 or above.")

# Edit D: three worked anchors for the exact missed shapes, appended to the anchors line (8).
ANCHORS_CDE = (" (c) `user['name']` assumes the key is present, so a missing key or a non-dict "
               "input raises KeyError or TypeError and crashes, so it rates 10 to 45 with "
               "notes to check the key is present and the value is a dict before access; "
               "(d) `b.decode('utf-8')` with no error handling raises UnicodeDecodeError on "
               "malformed bytes, so it rates 25 to 60 with notes to pass errors='replace' or "
               "catch the error; (e) `json.loads(s)` followed by per-item work with no size "
               "or count limit lets a huge or deeply-nested payload exhaust memory or CPU, so "
               "it rates 30 to 65 with notes to cap input size and item count before the loop.")

# Edit F: a recursion anchor (the adv-004 shape), appended to the anchors line.
ANCHOR_F = (" (f) a function that recurses on nested structure with no depth limit raises "
            "RecursionError on deeply-nested input, so it rates 20 to 55 with notes to add an "
            "explicit depth limit or convert to an iterative approach.")

# Edit C', the crash rule folded into the scope line (2) as a trailing clause.
SCOPE_CRASH = (" Remember that an uncaught crash on a constructible malformed input is a "
               "robustness failure in scope here, and such code can never rate 70 or above.")


def insert_crash(lines):
    out = list(lines)
    return out[:7] + [CRASH_LINE] + out[7:]


def append_anchors(lines):
    out = list(lines)
    out[8] = out[8] + ANCHORS_CDE
    return out


def append_recursion(lines):
    out = list(lines)
    out[8] = out[8] + ANCHOR_F
    return out


def bands_crash(lines):
    out = list(lines)
    out[6] = out[6] + " " + CRASH_LINE
    return out


def scope_crash(lines):
    out = list(lines)
    out[2] = out[2] + SCOPE_CRASH
    return out


def doc(lines) -> str:
    return "\n".join(lines) + "\n"


def build() -> dict:
    c: dict[str, list[str]] = {}
    c["round-01"] = insert_crash(BASE)                                  # Edit C only
    c["round-02"] = append_anchors(BASE)                               # Edit D only
    c["round-03"] = append_anchors(insert_crash(BASE))                 # C + D (expected best)
    c["round-04"] = append_recursion(append_anchors(insert_crash(BASE)))  # C + D + F
    c["round-05"] = append_recursion(append_anchors(BASE))            # D + F (no C)
    c["round-06"] = scope_crash(append_anchors(BASE))                # D + C' (scope clause)
    c["round-07"] = bands_crash(append_anchors(BASE))                # D + C in bands line
    c["round-08"] = insert_crash(append_recursion(BASE))             # C + F only
    c["round-09"] = append_recursion(scope_crash(append_anchors(insert_crash(BASE))))  # maximal
    c["round-10"] = append_anchors(insert_crash(BASE))               # clean C + D ship candidate
    return c


def main() -> int:
    out_dir = HERE / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    cands = build()
    for name, lines in cands.items():
        (out_dir / f"{name}.md").write_text(doc(lines))
    print(f"wrote {len(cands)} candidate docs to {out_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

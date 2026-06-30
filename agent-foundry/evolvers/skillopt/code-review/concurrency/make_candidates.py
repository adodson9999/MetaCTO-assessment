#!/usr/bin/env python3
"""Generate the 10 candidate skill docs for the concurrency improvement tournament.

Each candidate is the debate-gated baseline (concurrencylens_prompt.APPROVED_LINES) with ONE
or more bounded edits (extend an existing line / add a worked anchor), so every proposal is
auditable and clears the same "single-concern, deterministic-band language" bar the debate
gate enforces. The edits target the lens's middle/safe cases where a model is most likely to
drift off-band on the baseline:

  - CC-003 (two functions taking the same two locks in opposite orders — an AB-BA deadlock) —
    the baseline's single biggest miss: all four frameworks rate it ~70-75 because each
    function read on its own looks correctly locked, missing the lock-order inversion entirely.
                                                                          -> EDIT_DEADLOCK
  - CC-005 (a lock correctly held but spanning a blocking network call) — models tend to rate
    locked code high and miss the held-across-blocking-call smell.        -> EDIT_BLOCKING
  - CC-004 (check-then-act on a shared dict with no lock) — models often treat it as a minor
    nit instead of a real lost-write / duplicate-work race.               -> EDIT_CTA
  - CC-007 / CC-008 (a pure local function; a check-then-act fully under the lock) — models
    are prone to over-flagging safe code.                                 -> EDIT_SAFE
  - a worked anchor (d) pinning the AB-BA deadlock band.                  -> ANCHOR_D

The per-case baseline failures were read from the round-00 judged run before authoring these.

Output: candidates/round-01..round-10.md (round-00-baseline.md is written separately).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[3]
sys.path.insert(0, str(WS / "agents" / "common"))
import concurrencylens_prompt as p  # noqa: E402

BASE = list(p.APPROVED_LINES)

# Line indices in APPROVED_LINES (0-based):
#   2 = the "lower the rating only for issues this lens covers" enumeration
#   3 = the "never lower outside this lens" scope line
#   5 = the rating-scale / bands line
#   7 = the two-worked-anchors line

# EDIT_SAFE — appended to the scope line (L3): code with no shared mutable state is safe.
EDIT_SAFE = (" Code that has no shared mutable state is safe and rates in the 85 to 100 band — "
             "a pure function that touches only local variables and its arguments, or a "
             "check-then-act sequence performed entirely inside the lock, has no interleaving "
             "that can corrupt state, so do not lower its rating.")

# EDIT_BLOCKING — appended to the bands line (L5): a lock held across a blocking call.
EDIT_BLOCKING = (" Holding a lock across a blocking call — a network request, a disk read, or "
                 "a sleep — is a real problem in the 40 to 69 band even though no data is "
                 "corrupted, because it serializes every thread on that lock and can stall or "
                 "cascade timeouts; the fix is to do the blocking work outside the lock and "
                 "take the lock only to publish the result.")

# EDIT_CTA — appended to the lens-checks line (L2): check-then-act without the lock.
EDIT_CTA = (" In particular a check-then-act on shared state without the lock — testing a key "
            "is absent and then setting it, or testing then mutating — is a real problem, not "
            "a minor nit, because two threads can both pass the check and both write, losing "
            "or duplicating the update.")

# EDIT_DEADLOCK — appended to the bands line (L5): AB-BA lock-order inversion deadlocks.
EDIT_DEADLOCK = (" When two or more threads acquire the same two locks in opposite orders — "
                 "one takes lock a then lock b while another takes lock b then lock a — an "
                 "interleaving leaves each thread holding one lock and waiting forever for the "
                 "other, a deadlock that rates 1 to 30 (serious) even though each function read "
                 "on its own looks correctly locked; the fix is to make every thread acquire "
                 "the locks in one single global order.")

# ANCHOR_D — a worked anchor (d) for the AB-BA deadlock, appended to the anchors line (L7).
ANCHOR_D = (' (d) one function doing `with a:` then `with b:` while another does `with b:` '
            'then `with a:` is an AB-BA lock-order inversion: an interleaving where each grabs '
            'its first lock then blocks forever on the second is a guaranteed deadlock, so it '
            'rates 1 to 30 with notes to acquire a and b in one consistent global order in '
            'every function.')

# ANCHOR_C — a worked anchor (c) for the held-across-blocking-call case, appended to L7.
ANCHOR_C = (' (c) `with lock:\\n    resp = requests.get(url, timeout=30)\\n    cache[url] = '
            'resp.text` guards the shared cache correctly but holds the lock across a blocking '
            'network call, so every other thread blocks for the whole request and a slow or '
            'hung server stalls them all; this rates 45 to 70 with notes to move the '
            'requests.get outside the lock and take the lock only to write cache[url].')

# A standalone reinforcement line for the maximal round.
SAFE_LINE = ("Synchronization that fully covers every read and write of a shared field — the "
             "same lock around all accessors, or a thread-safe primitive used as intended — "
             "leaves no interleaving that can lose an update, and rates in the 85 to 100 band.")


def with_safe(lines):
    out = list(lines)
    out[3] = out[3] + EDIT_SAFE
    return out


def with_blocking(lines):
    out = list(lines)
    out[5] = out[5] + EDIT_BLOCKING
    return out


def with_cta(lines):
    out = list(lines)
    out[2] = out[2] + EDIT_CTA
    return out


def with_deadlock(lines):
    out = list(lines)
    out[5] = out[5] + EDIT_DEADLOCK
    return out


def with_anchor_c(lines):
    out = list(lines)
    out[7] = out[7] + ANCHOR_C
    return out


def with_anchor_d(lines):
    out = list(lines)
    out[7] = out[7] + ANCHOR_D
    return out


def doc(lines) -> str:
    return "\n".join(lines) + "\n"


# --- ordered candidate list (10 rounds) ---------------------------------------------- #
def build() -> dict:
    cands: dict[str, list[str]] = {}

    # r01: DEADLOCK only (targets CC-003 — the baseline's biggest miss).
    cands["round-01"] = with_deadlock(BASE)
    # r02: SAFE only (stop over-flagging CC-007 / CC-008).
    cands["round-02"] = with_safe(BASE)
    # r03: BLOCKING only (pin CC-005 into 45-70).
    cands["round-03"] = with_blocking(BASE)
    # r04: CTA only (pin CC-004 as a real problem).
    cands["round-04"] = with_cta(BASE)
    # r05: DEADLOCK + SAFE.
    cands["round-05"] = with_safe(with_deadlock(BASE))
    # r06: DEADLOCK + SAFE + BLOCKING.
    cands["round-06"] = with_blocking(with_safe(with_deadlock(BASE)))
    # r07: DEADLOCK + SAFE + BLOCKING + CTA — all four scope clarifications (likely best).
    cands["round-07"] = with_cta(with_blocking(with_safe(with_deadlock(BASE))))
    # r08: all four + worked anchors (c) and (d).
    cands["round-08"] = with_anchor_d(with_anchor_c(with_cta(with_blocking(with_safe(with_deadlock(BASE))))))
    # r09: maximal guidance — all edits + both anchors + a standalone reinforcement line.
    cands["round-09"] = with_anchor_d(with_anchor_c(with_cta(with_blocking(with_safe(with_deadlock(BASE)))))) + [SAFE_LINE]
    # r10: the cleanest combined doc (DEADLOCK + SAFE + BLOCKING + CTA), the intended ship candidate.
    cands["round-10"] = with_cta(with_blocking(with_safe(with_deadlock(BASE))))

    return cands


def main() -> int:
    out_dir = HERE / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    # round 0 baseline = the debate-gated APPROVED_PROMPT, verbatim.
    (out_dir / "round-00-baseline.md").write_text(doc(BASE))
    cands = build()
    for name, lines in cands.items():
        (out_dir / f"{name}.md").write_text(doc(lines))
    print(f"wrote round-00-baseline.md + {len(cands)} candidate docs to {out_dir}")
    for name in ["round-00-baseline", *cands.keys()]:
        print(f"  - {name}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

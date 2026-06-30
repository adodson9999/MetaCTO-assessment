#!/usr/bin/env python3
"""Generate the candidate skill docs for the chaos-engineering improvement tournament.

Each candidate is the debate-gated baseline (chaos_prompt.APPROVED_LINES) with ONE bounded
edit (replace the soft calibration-anchor tail of the bands line, and/or append a single
standalone calibration-floor line), so every proposal is auditable and clears the same
"single-concern, deterministic-band language" bar the debate gate enforces.

The proposing agent (the orchestrator) derived these from the baseline judged run's per-case
failures: on the seed case chaos-001 (`@circuit_breaker(fallback=cached_quote)` +
`timeout=1.0`, gold band [85,100]) three of four frameworks rated 75-78 — below band —
because the soft anchor let them deduct for a missing retry jitter / health metric. langgraph
already lands 85. Every edit therefore strengthens the SAME high-band anchor so the
three-core-protections pattern (timeout AND fallback/cache AND circuit-breaker/bulkhead)
reliably lands >=85, without touching the low-protection cases (chaos-002/004/005 carry fewer
than the three protections, so the anchor never fires on them).

Output: candidates/round-01..round-10.md (round-00-baseline.md is written separately).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[3]
sys.path.insert(0, str(WS / "agents" / "common"))
import chaos_prompt as p  # noqa: E402

BASE = list(p.APPROVED_LINES)

# The bands line (index 6) already ends with a SOFT calibration anchor that begins at this
# marker. Edits replace that soft tail with a stronger, directive one.
ANCHOR_MARKER = "; as a calibration anchor"

# --- the bounded edit fragments ------------------------------------------------------ #
# STRONG_TAIL: a directive (MUST) replacement for the soft anchor on the bands line.
STRONG_TAIL = (
    "; as a calibration anchor you MUST rate at 85 or above any dependency call that already "
    "carries a timeout AND a fallback or cache AND a circuit breaker or bulkhead, because that "
    "combination is the complete set of core chaos protections — the absence of retry jitter, "
    "an explicit health metric, or a second redundant mechanism is at most a minor deduction "
    "kept inside the 85 to 99 range, and you drop below 85 only when you can name a specific "
    "injected fault that still cascades into a full outage or wedges the path with no recovery."
)

# STRONG_TAIL_V2: same rule, reworded (a second deterministic phrasing for robustness rounds).
STRONG_TAIL_V2 = (
    "; as a calibration anchor, a timeout AND a fallback or cache AND a circuit breaker or "
    "bulkhead together are the complete set of core chaos protections, so code that already "
    "has all three on its dependency call belongs at 85 or above and you never deduct below "
    "85 for a merely missing retry jitter, health metric, or redundant mechanism — go below "
    "85 only to name a specific injected fault that still cascades into a full outage or wedges "
    "the path with no recovery."
)

# FLOOR_LINE: a single standalone calibration-floor line, appended (single concern).
FLOOR_LINE = (
    "Calibration floor: when a dependency call is wrapped with a timeout and a fallback or "
    "cache and a circuit breaker or bulkhead, every core chaos protection is present and the "
    "rating is 85 or higher unless you can name a specific injected fault that still cascades "
    "or wedges the path."
)

# FLOOR_LINE_V2: the same floor, reworded.
FLOOR_LINE_V2 = (
    "Calibration floor: a dependency call carrying a timeout, a fallback or cache, and a "
    "circuit breaker or bulkhead has the full set of core chaos protections and rates at least "
    "85; only a specific named injected fault that still cascades into an outage or wedges the "
    "path may drop it lower."
)


def _replace_anchor(lines: list[str], strong_tail: str) -> list[str]:
    """Replace the soft anchor tail of the bands line (index 6) with a stronger one."""
    out = list(lines)
    head = out[6].split(ANCHOR_MARKER, 1)[0]
    out[6] = head + strong_tail
    return out


def with_strong(lines, v2: bool = False):
    return _replace_anchor(lines, STRONG_TAIL_V2 if v2 else STRONG_TAIL)


def with_floor(lines, v2: bool = False):
    return list(lines) + [FLOOR_LINE_V2 if v2 else FLOOR_LINE]


def doc(lines) -> str:
    return "\n".join(lines) + "\n"


# --- ordered candidate list (10 rounds) ---------------------------------------------- #
def build() -> dict:
    cands: dict[str, list[str]] = {}

    # r01: strengthen the anchor in place (the primary lever).
    cands["round-01"] = with_strong(BASE)
    # r02: baseline + a standalone floor line only.
    cands["round-02"] = with_floor(BASE)
    # r03: strong anchor + standalone floor (maximal, expected ceiling).
    cands["round-03"] = with_floor(with_strong(BASE))
    # r04: strong anchor, reworded (V2).
    cands["round-04"] = with_strong(BASE, v2=True)
    # r05: baseline + floor line, reworded (V2).
    cands["round-05"] = with_floor(BASE, v2=True)
    # r06: strong anchor V2 + floor V2.
    cands["round-06"] = with_floor(with_strong(BASE, v2=True), v2=True)
    # r07: strong anchor + floor (dup of r03 wording — robustness re-confirm).
    cands["round-07"] = with_floor(with_strong(BASE))
    # r08: strong anchor V2 + floor V1 (mixed).
    cands["round-08"] = with_floor(with_strong(BASE, v2=True))
    # r09: strong anchor V1 + floor V2 (mixed).
    cands["round-09"] = with_floor(with_strong(BASE), v2=True)
    # r10: the cleanest ship candidate — strong anchor + floor.
    cands["round-10"] = with_floor(with_strong(BASE))

    return cands


def main() -> int:
    out_dir = HERE / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    # round-00 baseline = the live debate-gated prompt, verbatim.
    (out_dir / "round-00-baseline.md").write_text(doc(BASE))
    cands = build()
    for name, lines in cands.items():
        (out_dir / f"{name}.md").write_text(doc(lines))
    print(f"wrote round-00-baseline.md + {len(cands)} candidate docs to {out_dir}")
    for name in cands:
        print(f"  - {name}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

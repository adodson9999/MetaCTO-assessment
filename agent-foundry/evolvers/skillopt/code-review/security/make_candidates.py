#!/usr/bin/env python3
"""Generate the 10 candidate skill docs for the security improvement tournament.

Each candidate is the debate-gated baseline (security_prompt.APPROVED_LINES) with ONE
bounded edit (add / replace a line), so every proposal is auditable and clears the same
"single-concern, deterministic-band language" bar the debate gate enforces. The proposing
agent (the orchestrator) derived these from the baseline judged run's per-case failures:
langgraph rated sec-006 (wildcard CORS + credentials) 75 vs band [40,70] (too lenient) and
sec-008 (clean env-sourced secret) 70 vs band [80,100] (too harsh). Edit A targets the
former, Edit B the latter; later rounds combine and reword them.

Output: candidates/round-01..round-10.md (round-00-baseline.md is written separately).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parents[3]
sys.path.insert(0, str(WS / "agents" / "common"))
import security_prompt as p  # noqa: E402

BASE = list(p.APPROVED_LINES)

# --- the two bounded edit fragments -------------------------------------------------- #
# Edit B: a secret read from the environment / a secret manager is the secure pattern, and
# out-of-lens validation gaps are never penalised. Appended to the scope-only line (L2).
EDIT_B = (" Reading a secret from an environment variable or a secret manager is the secure "
          "pattern, not an exposure, and you never lower the rating for missing input "
          "validation, type-checking, or sanitisation that does not itself create an "
          "injection, a secret exposure, a missing authorization check, or an insecure "
          "default.")

# Edit A: a third worked anchor (c) pinning wildcard CORS + credentials into the 40-69 band.
ANCHOR_C = (' (c) `Access-Control-Allow-Origin: *` set together with '
            '`Access-Control-Allow-Credentials: true` is an insecure default that exposes '
            'authenticated, credentialed responses to any origin, a real problem rather '
            'than a minor nit, so it rates 40 to 69 with notes naming an explicit '
            'allow-list of trusted origins (and dropping the wildcard whenever credentials '
            'are allowed) as the fix.')

# Edit A': the same CORS severity guidance folded into the bands line (L6) instead.
BANDS_CORS = (' Treat an insecure default that exposes authenticated data across origins '
              '(wildcard CORS with credentials) as a real problem in the 40 to 69 band, '
              'not a 70 to 89 weakness.')

# A standalone reinforcement line for the strongest rounds.
SECRET_LINE = ("A secret sourced from an environment variable or a secret manager and used "
               "as intended is secure and rates in the 80 to 100 band; only a hard-coded "
               "secret literal or a secret written to logs is an exposure.")


def with_edit_B(lines):
    out = list(lines)
    out[2] = out[2] + EDIT_B
    return out


def with_anchor_C(lines):
    out = list(lines)
    out[8] = out[8] + ANCHOR_C
    return out


def with_bands_cors(lines):
    out = list(lines)
    out[6] = out[6] + BANDS_CORS
    return out


def doc(lines) -> str:
    return "\n".join(lines) + "\n"


# --- ordered candidate list (10 rounds) ---------------------------------------------- #
def build() -> dict:
    cands: dict[str, list[str]] = {}

    # r01: Edit B only (targets sec-008).
    cands["round-01"] = with_edit_B(BASE)
    # r02: Edit A only — anchor (c) (targets sec-006).
    cands["round-02"] = with_anchor_C(BASE)
    # r03: Edit A + Edit B combined (expected best).
    cands["round-03"] = with_anchor_C(with_edit_B(BASE))
    # r04: Edit B + the CORS guidance in the bands line instead of an anchor.
    cands["round-04"] = with_bands_cors(with_edit_B(BASE))
    # r05: Edit A' (bands-line CORS) only.
    cands["round-05"] = with_bands_cors(BASE)
    # r06: combined A+B + a standalone secret-is-secure line appended.
    cands["round-06"] = with_anchor_C(with_edit_B(BASE)) + [SECRET_LINE]
    # r07: combined A+B + both CORS placements (anchor AND bands line) — robustness.
    cands["round-07"] = with_bands_cors(with_anchor_C(with_edit_B(BASE)))
    # r08: Edit B + standalone secret line (no CORS change) — isolate which helps sec-008.
    cands["round-08"] = with_edit_B(BASE) + [SECRET_LINE]
    # r09: combined A+B + standalone secret line + bands CORS — maximal guidance.
    cands["round-09"] = with_bands_cors(with_anchor_C(with_edit_B(BASE))) + [SECRET_LINE]
    # r10: the cleanest combined doc (A anchor + B), the intended ship candidate.
    cands["round-10"] = with_anchor_C(with_edit_B(BASE))

    return cands


def main() -> int:
    out_dir = HERE / "candidates"
    out_dir.mkdir(parents=True, exist_ok=True)
    cands = build()
    for name, lines in cands.items():
        (out_dir / f"{name}.md").write_text(doc(lines))
    print(f"wrote {len(cands)} candidate docs to {out_dir}")
    for name in cands:
        print(f"  - {name}.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

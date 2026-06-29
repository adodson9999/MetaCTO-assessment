#!/usr/bin/env python3
"""Determinism review — every AI artifact must be stable across samples.

Compares N samples of the same AI action (constitution Article I.8,
references/determinism.md). The COMPARISON is pure Python; only producing the
samples uses the model (done by the caller, which passes the sample files in).

Verdict: deterministic | stable-within-tolerance | non-deterministic.
Writes a receipt to results/_global/determinism/<artifact>-<ts>.json.

Usage:
    python scripts/determinism_check.py --artifact ID --kind KIND \\
        --samples s1.json s2.json ... [--essential k1 k2] [--workspace DIR]
Exit 0 if deterministic / stable-within-tolerance, 1 if non-deterministic.
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path


def canon(obj, essential: list[str] | None):
    """Reduce to the part that must be stable, then to a canonical string."""
    if essential and isinstance(obj, dict):
        obj = {k: obj[k] for k in essential if k in obj}
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def load(p: str):
    text = Path(p).read_text(encoding="utf-8", errors="replace").strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text  # prompt / freeform: compare raw text


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--artifact", required=True)
    ap.add_argument("--kind", default="generic")
    ap.add_argument("--samples", nargs="+", required=True)
    ap.add_argument("--essential", nargs="*", default=None)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()

    canons = [canon(load(s), args.essential) for s in args.samples]
    unique = sorted(set(canons))
    if len(unique) == 1:
        verdict = "deterministic"
    elif len(unique) <= max(1, len(canons) // 3):
        verdict = "stable-within-tolerance"
    else:
        verdict = "non-deterministic"

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    rec = {
        "artifact": args.artifact, "kind": args.kind, "samples": len(args.samples),
        "distinct": len(unique), "verdict": verdict, "ts": ts,
    }
    out = Path(args.workspace) / "results" / "_global" / "determinism"
    out.mkdir(parents=True, exist_ok=True)
    (out / f"{args.artifact}-{ts}.json").write_text(json.dumps(rec, indent=2))

    print(json.dumps(rec, indent=2))
    if verdict == "non-deterministic":
        print("\nNON-DETERMINISTIC: do not adopt. Return prompt line to the debate "
              "gate / make the metric deterministic / discard the revision.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

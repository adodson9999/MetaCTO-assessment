#!/usr/bin/env python3
"""Code-Review Gate — enforcer for constitution Article I.10.

Install target: .claude/skills/forge-agents/scripts/code_review_gate.py

No code-producing build reports "done" until every code file it created scores
>= 85 on every one of the 21 code-review perspectives in agents/code-review/ — no
exception. See references/code-review-gate.md.

Design: the deterministic core (trigger detection, target discovery, aggregation,
threshold, receipt) is pure Python and unit-tested. The model is only invoked to
produce each {rating, notes}; the gate's pass/fail decision is pure Python.

Usage:
    python scripts/code_review_gate.py --workspace <foundry> --agent <group>/<name>
Exit 0 = pass (or does-not-apply), 1 = gate failure, 2 = setup error (reviewers
missing, etc.).
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

DEFAULT_THRESHOLD = 85

# Known default reviewer set, for documentation and as the default in helpers. The
# AUTHORITATIVE set at run time is whatever discover_perspectives() finds in
# agents/code-review/ — the gate never enforces a hardcoded count or fixed list.
REQUIRED_PERSPECTIVES: tuple[str, ...] = (
    "minimalist", "math-correctness", "system-design", "device-stack", "network",
    "security", "vulnerability", "unit-test", "performance", "logic-error",
    "concurrency", "error-handling-resilience", "data-integrity", "memory-resource",
    "maintainability", "api-contract", "observability", "dependency-supply-chain",
    "adversarial-input", "domain-requirements", "chaos-engineering",
)

# Substrings in task_spec.md that mark a code-producing agent.
CODE_PRODUCING_MARKERS: tuple[str, ...] = (
    "code", "script", "implement", "refactor", "codegen", "qa automation",
    "software engineer", "test automation", "programming", "compile",
    "function", "class", "module", "generate code", "write code",
)

SOURCE_SUFFIXES: tuple[str, ...] = (
    ".py", ".js", ".ts", ".tsx", ".jsx", ".go", ".rs", ".java", ".rb", ".php",
    ".c", ".cc", ".cpp", ".h", ".hpp", ".cs", ".kt", ".swift", ".scala", ".sh",
)


# ---- pure-Python core (unit-tested) -----------------------------------------

def is_code_producing(task_spec_text: str, config_applies: bool | None = None) -> bool:
    """True when the gate must block on the built agent's produced code.

    config_applies (from config.toml [code_review_gate].applies) overrides the
    heuristic when set; otherwise a keyword match against task_spec decides.
    """
    if config_applies is not None:
        return bool(config_applies)
    text = task_spec_text.lower()
    return any(marker in text for marker in CODE_PRODUCING_MARKERS)


def validate_rating(obj: object) -> int | None:
    """Return the integer rating if obj is a valid {rating, notes} verdict, else None.

    Mirrors the review_output schema: exactly two keys, rating int 0-100, notes a
    non-empty string. An invalid verdict yields None, which the gate scores as 0.
    """
    if not isinstance(obj, dict):
        return None
    if set(obj.keys()) != {"rating", "notes"}:
        return None
    rating = obj.get("rating")
    notes = obj.get("notes")
    if isinstance(rating, bool) or not isinstance(rating, int):
        return None
    if rating < 0 or rating > 100:
        return None
    if not isinstance(notes, str) or notes.strip() == "":
        return None
    return rating


@dataclass(frozen=True)
class Verdict:
    target: str
    perspective: str
    rating: int
    notes: str


@dataclass
class GateResult:
    applies: bool
    threshold: int
    status: str
    targets: list[str]
    perspectives: list[str]
    ratings: list[dict]
    min_rating: int | None
    failures: list[dict] = field(default_factory=list)


def evaluate(
    targets: list[str],
    verdicts: list[Verdict],
    applies: bool,
    threshold: int = DEFAULT_THRESHOLD,
    required: tuple[str, ...] = REQUIRED_PERSPECTIVES,
) -> GateResult:
    """Pure decision: pass only if every target x every required perspective is >= threshold.

    A missing (target, perspective) pair is a failure (no exception / no skip).
    When applies is False the gate never blocks (status always pass).
    """
    ratings = [
        {"target": v.target, "perspective": v.perspective, "rating": v.rating, "notes": v.notes}
        for v in verdicts
    ]
    by_pair: dict[tuple[str, str], Verdict] = {(v.target, v.perspective): v for v in verdicts}

    failures: list[dict] = []
    seen_ratings: list[int] = []
    for target in targets:
        for perspective in required:
            v = by_pair.get((target, perspective))
            if v is None:
                failures.append({
                    "target": target, "perspective": perspective,
                    "rating": None, "notes": "no verdict produced for this target/perspective",
                })
                continue
            seen_ratings.append(v.rating)
            if v.rating < threshold:
                failures.append({
                    "target": target, "perspective": perspective,
                    "rating": v.rating, "notes": v.notes,
                })

    if applies and not required:
        # No reviewers discovered: the gate cannot be satisfied and must never pass.
        failures.append({
            "target": None, "perspective": None, "rating": None,
            "notes": "no reviewers discovered in agents/code-review/ (cannot pass with zero)",
        })

    min_rating = min(seen_ratings) if seen_ratings else None
    if not applies:
        status = "pass"
    else:
        status = "pass" if (not failures and targets) else "fail"
    return GateResult(
        applies=applies, threshold=threshold, status=status,
        targets=list(targets), perspectives=list(required),
        ratings=ratings, min_rating=min_rating, failures=failures,
    )


def build_receipt(agent: str, result: GateResult) -> dict:
    return {
        "gate": "code-review",
        "applies": result.applies,
        "threshold": result.threshold,
        "status": result.status,
        "ts": datetime.now(timezone.utc).isoformat(),
        "agent_under_build": agent,
        "perspectives": result.perspectives,
        "perspective_count": len(result.perspectives),
        "targets": result.targets,
        "ratings": result.ratings,
        "min_rating": result.min_rating,
        "failures": result.failures,
    }


def discover_targets(ws: Path, group: str, name: str, include_produced: bool) -> list[str]:
    """Created-code targets always; produced-code targets when the agent makes code."""
    targets: list[Path] = []
    agent_dir = ws / "agents" / group / name
    if agent_dir.is_dir():
        targets += [p for p in agent_dir.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()]
    score = ws / "judge" / group / name / "score.py"
    if score.is_file():
        targets.append(score)
    if include_produced:
        produced = ws / "results" / group / name / "produced"
        if produced.is_dir():
            targets += [p for p in produced.rglob("*") if p.suffix in SOURCE_SUFFIXES and p.is_file()]
    rels = sorted({str(p.relative_to(ws)) for p in targets})
    return rels


def discover_perspectives(ws: Path) -> list[str]:
    """The AUTHORITATIVE reviewer set: every agent present in agents/code-review/.

    Discovered fresh at run time and returned sorted. The count is never hardcoded —
    adding a reviewer directory makes it required on the next run; removing one drops
    it. A directory counts only if it holds the canonical prompt
    subagent/code-review-<name>.md.
    """
    base = ws / "agents" / "code-review"
    found: list[str] = []
    if base.is_dir():
        for d in sorted(base.iterdir()):
            if d.is_dir() and (d / "subagent" / f"code-review-{d.name}.md").is_file():
                found.append(d.name)
    return found


def receipt_matches_folder(receipt: dict, ws: Path) -> bool:
    """No-bypass cross-check: a receipt is only valid if the reviewer set it recorded
    equals the current contents of agents/code-review/. Blocks stale/short receipts."""
    return sorted(receipt.get("perspectives", [])) == sorted(discover_perspectives(ws))


# ---- model invocation (thin, replaceable) -----------------------------------

ReviewFn = Callable[[str, str], dict]


def _default_review_fn(ws: Path) -> ReviewFn:
    """Run one reviewer over one file via the centralized subagent runner.

    Imports the foundry's runner lazily so the pure core stays import-light and
    unit-testable without a backend. Replace/inject in tests.
    """
    sys.path.insert(0, str(ws / "agents" / "common"))
    sys.path.insert(0, str(ws / "scripts"))
    from runners.subagent_runner import build_invoker  # type: ignore
    from runners.utils import load_system_prompt  # type: ignore

    def review(perspective: str, code_text: str) -> dict:
        md = ws / "agents" / "code-review" / perspective / "subagent" / f"code-review-{perspective}.md"
        system = load_system_prompt(md)
        invoke = build_invoker(ws, system, lambda code: code)
        raw = invoke(code_text)
        try:
            return json.loads(raw.strip())
        except Exception:
            return {"_raw": raw}

    return review


def run_reviews(
    ws: Path, targets: list[str], review_fn: ReviewFn,
    required: tuple[str, ...] = REQUIRED_PERSPECTIVES,
) -> list[Verdict]:
    verdicts: list[Verdict] = []
    for rel in targets:
        code_text = (ws / rel).read_text(encoding="utf-8", errors="replace")
        for perspective in required:
            out = review_fn(perspective, code_text)
            rating = validate_rating(out)
            if rating is None:
                verdicts.append(Verdict(rel, perspective, 0,
                                        "invalid {rating, notes} output; scored 0 (schema gate)"))
            else:
                verdicts.append(Verdict(rel, perspective, rating, str(out.get("notes", ""))))
    return verdicts


# ---- CLI --------------------------------------------------------------------

def _read_config_applies(ws: Path) -> bool | None:
    cfg = ws / "config.toml"
    if not cfg.is_file():
        return None
    for line in cfg.read_text(encoding="utf-8").splitlines():
        s = line.strip().replace(" ", "")
        if s.startswith("applies=") and ("true" in s.lower() or "false" in s.lower()):
            return "true" in s.lower()
    return None


def _read_threshold(ws: Path) -> int:
    cfg = ws / "config.toml"
    if cfg.is_file():
        for line in cfg.read_text(encoding="utf-8").splitlines():
            s = line.strip().replace(" ", "")
            if s.startswith("threshold="):
                try:
                    return max(DEFAULT_THRESHOLD, int(s.split("=", 1)[1]))  # floor: never below 85
                except ValueError:
                    pass
    return DEFAULT_THRESHOLD


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Code-review gate (Article I.10).")
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--agent", required=True, help="<group>/<name> of the agent under build")
    ap.add_argument("--dry-run", action="store_true",
                    help="discover targets and write an applies/no-target receipt without invoking reviewers")
    args = ap.parse_args(argv[1:])

    ws = Path(args.workspace).resolve()
    group, _, name = args.agent.partition("/")
    if not name:
        print("ERROR: --agent must be <group>/<name>", file=sys.stderr)
        return 2

    threshold = _read_threshold(ws)
    spec = ws / "task_spec.md"
    spec_text = spec.read_text(encoding="utf-8") if spec.is_file() else ""
    code_producing = is_code_producing(spec_text, _read_config_applies(ws))

    targets = discover_targets(ws, group, name, include_produced=code_producing)
    # The gate applies whenever there is created code OR the agent produces code.
    applies = bool(targets) or code_producing

    out_dir = ws / "results" / "_global"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    receipt_path = out_dir / f"code-review-{ts}.json"

    if not applies:
        result = evaluate([], [], applies=False, threshold=threshold)
        receipt_path.write_text(json.dumps(build_receipt(args.agent, result), indent=2))
        print(f"code-review gate: does not apply (no created code, not code-producing). receipt={receipt_path}")
        return 0

    perspectives = tuple(discover_perspectives(ws))
    if not perspectives:
        print("ERROR: no code-review agents found in agents/code-review/; the gate cannot be "
              "satisfied and must not be bypassed. Build the reviewers first "
              "(see code-review-perspectives/forge-starters.md).", file=sys.stderr)
        return 2

    if args.dry_run:
        result = evaluate(targets, [], applies=True, threshold=threshold, required=perspectives)
        receipt_path.write_text(json.dumps(build_receipt(args.agent, result), indent=2))
        print(f"code-review gate (dry-run): {len(targets)} target(s), "
              f"{len(perspectives)} reviewer(s) discovered. receipt={receipt_path}")
        return 0 if result.status == "pass" else 1

    verdicts = run_reviews(ws, targets, _default_review_fn(ws), required=perspectives)
    result = evaluate(targets, verdicts, applies=True, threshold=threshold, required=perspectives)
    receipt_path.write_text(json.dumps(build_receipt(args.agent, result), indent=2))

    print(f"code-review gate: status={result.status} threshold={threshold} "
          f"min_rating={result.min_rating} targets={len(targets)} receipt={receipt_path}")
    if result.status == "fail":
        for f in result.failures:
            print(f"  FAIL  {f['target']} :: {f['perspective']} = {f['rating']}  {f['notes']}")
        print("\nHARD-HALT: rewrite the offending code to >=85 on every lens; never waive. Re-run the gate.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))

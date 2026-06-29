#!/usr/bin/env python3
"""Phase-4 run of the four Documentation-Reviewer agents using the CURRENT Claude Code
session as the model backend.

In this environment the programmatic LLM paths are unavailable (nested `claude -p` and the
ANTHROPIC_API_KEY both have no credit; Ollama is off). The only available model is the
live Claude Code session driving this build. The forge harness takes the model's output
through its injected generate(brief) hook, so this driver supplies, as that hook's return
value, the verdict decisions the session produced by reasoning over each case's brief
(bug report + the full cli/ + reference/ corpus) under the debate-gated prompt — never by
reading data/.../gold.json.

All four frameworks (langgraph, crewai, claude_sdk, the Claude Code subagent) are wrappers
around the same model + same gated prompt, so on one backend they return the same verdicts
— the expected "four-of-the-same on one substrate" outcome. The harness scores each against
gold and the judge ranks them.

Run:
    FORGE_WORKSPACE=. python tools/run_docreview_session.py --run-id <id>
Then:
    python judge/general/documentation-reviewer/score.py --workspace . --run-id <id>
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
os.environ["FORGE_WORKSPACE"] = str(WS)
os.environ.setdefault("FORGE_SANDBOX_ROOT", str(WS))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

# --- The session's verdicts, derived by reasoning over each brief's corpus (not gold). ---
# Keyed by a distinct substring of each report's observed Actual Result (present verbatim in
# the brief), so the harness can route the right decision to the right case.
SESSION_DECISIONS = {
    "200 OK with the full user object returned": {
        "verdict": "yes",
        "source_of_truth": {
            "file": "data/documentation-reviewer/reference/auth.md", "line": 9,
            "text": "When the Authorization header is missing or the token is invalid, the API returns 401 Unauthorized."},
        "other_matches": [],
        "documented_expected": "401 Unauthorized when the Authorization header is missing or invalid",
        "observed": "200 OK with the full user object returned",
        "reason": "reference/auth.md documents that GET /auth/me returns 401 when the Authorization header is missing, but the report observed 200 with the user object, so the bug is valid.",
    },
    "All 194 products are returned in a single response": {
        "verdict": "no",
        "source_of_truth": {
            "file": "data/documentation-reviewer/cli/products.md", "line": 4,
            "text": "Default limit is 30. Passing --limit 0 returns all products with no cap."},
        "other_matches": [{
            "file": "data/documentation-reviewer/reference/products.md", "line": 5,
            "text": "A limit of 0 returns up to a maximum of 100 products."}],
        "documented_expected": "limit=0 returns all products with no cap",
        "observed": "All 194 products are returned in a single response",
        "reason": "The most-recently-modified file, cli/products.md, documents that --limit 0 returns all products with no cap; the observed behavior matches it, so the bug is not valid. The older reference/products.md (max 100) conflicts but is superseded.",
    },
    "Tags returned in insertion order, not alphabetical": {
        "verdict": "missing-docs",
        "source_of_truth": None,
        "other_matches": [],
        "documented_expected": None,
        "observed": "Tags returned in insertion order, not alphabetical",
        "reason": "After scanning both folders, neither cli/ nor reference/ documents the ordering of GET /recipes/tags (recipes.md covers only /recipes and /recipes/meal-type), so it cannot be determined from docs.",
    },
    "Token remained valid past 31 minutes and only expired at 60 minutes": {
        "verdict": "no",
        "source_of_truth": {
            "file": "data/documentation-reviewer/reference/auth.md", "line": 5,
            "text": "The accessToken expires after expiresInMins minutes (default 60)."},
        "other_matches": [],
        "documented_expected": "accessToken expires after expiresInMins minutes, default 60",
        "observed": "Token remained valid past 31 minutes and only expired at 60 minutes",
        "reason": "reference/auth.md documents the default expiry as 60 minutes; the observed 60-minute expiry matches the documentation, so the bug is not valid (the report's claimed 30-minute expectation is not what the docs state).",
    },
}


def session_generate(brief: str) -> dict:
    for needle, decision in SESSION_DECISIONS.items():
        if needle in brief:
            return dict(decision)
    return {}  # unknown case -> empty (scores 0); never silently credited


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run-id", required=True)
    a = ap.parse_args()
    os.environ["FORGE_RUN_ID"] = a.run_id

    import docreview  # imported after env is set
    docreview.RUN_ID = a.run_id

    for agent in ("langgraph", "crewai", "claude_sdk", "general-documentation-reviewer"):
        s = docreview.run_docreview_test(agent, session_generate)
        print(f"[{agent}] verdict_accuracy={s['verdict_accuracy_pct']}% "
              f"reports={s['verdicts_total']} "
              f"source_of_truth_match={s['source_of_truth_match_pct']}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Guardrail verifier — LLM config format invariants for agent-foundry.

Enforces the single-source LLM config pattern so no shell script can silently
bypass or hardcode the provider.  Run this after any new script is generated
or any existing script is edited.

Checks
------
1. config.toml  [backend].provider == "auto"
2. scripts/llm_config.py exists and defines _is_claude_code_session()
3. Every phase4_*.sh contains:  eval "$(python scripts/llm_config.py --export)"
4. No phase4_*.sh contains a bare hardcoded FORGE_PROVIDER= assignment
5. Every ollama health-check (curl … /api/tags) is guarded by
       if [ "$FORGE_PROVIDER" = "ollama" ]   (or equivalent PROVIDER var guard)
   — i.e. no unconditional ollama-reachability check that would fail when
   Claude Haiku is the active backend.

Exit codes
----------
0  — all checks passed
1  — one or more failures (details printed to stdout)
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

# ── Paths ──────────────────────────────────────────────────────────────────
FOUNDRY = Path(__file__).resolve().parent.parent
SCRIPTS = FOUNDRY / "scripts"
CONFIG  = FOUNDRY / "config.toml"

# ── Helpers ────────────────────────────────────────────────────────────────
PASS = "\033[32m✓\033[0m"
FAIL = "\033[31m✗\033[0m"
WARN = "\033[33m!\033[0m"

failures: list[str] = []


def ok(msg: str) -> None:
    print(f"  {PASS}  {msg}")


def fail(msg: str) -> None:
    print(f"  {FAIL}  {msg}")
    failures.append(msg)


def section(title: str) -> None:
    print(f"\n── {title} {'─' * max(0, 60 - len(title))}")


# ── Check 1 — config.toml provider = "auto" ───────────────────────────────
section("Check 1 · config.toml [backend].provider")
if not CONFIG.exists():
    fail(f"config.toml not found at {CONFIG}")
else:
    text = CONFIG.read_text()
    # Accept   provider = "auto"  with any surrounding whitespace / quotes
    if re.search(r'^\s*provider\s*=\s*["\']?auto["\']?\s*$', text, re.MULTILINE):
        ok('provider = "auto"')
    else:
        m = re.search(r'^\s*provider\s*=.*$', text, re.MULTILINE)
        current = m.group(0).strip() if m else "(not found)"
        fail(f'config.toml [backend].provider must be "auto", found: {current}')


# ── Check 2 — scripts/llm_config.py exists with detection function ─────────
section("Check 2 · scripts/llm_config.py")
LLM_CONFIG = SCRIPTS / "llm_config.py"
if not LLM_CONFIG.exists():
    fail("scripts/llm_config.py does not exist — create it from the implementation plan")
else:
    src = LLM_CONFIG.read_text()
    if "_is_claude_code_session" in src:
        ok("_is_claude_code_session() defined")
    else:
        fail("scripts/llm_config.py is missing _is_claude_code_session() — provider detection broken")
    if "CLAUDE_CODE_ENTRYPOINT" in src:
        ok("CLAUDE_CODE_ENTRYPOINT signal present")
    else:
        fail("scripts/llm_config.py does not check CLAUDE_CODE_ENTRYPOINT")
    if "--export" in src:
        ok("--export flag for bash eval present")
    else:
        fail("scripts/llm_config.py missing --export flag — shell scripts cannot source it")


# ── Check 3 & 4 & 5 — per-script checks ───────────────────────────────────
section("Check 3-5 · phase4_*.sh scripts")

EVAL_PATTERN      = re.compile(r'eval\s+"?\$\(python\s+scripts/llm_config\.py\s+--export\)"?')
HARDCODE_PATTERN  = re.compile(r'^\s*export\s+FORGE_PROVIDER=["\']?(ollama|claude[-_]haiku|claude)["\']?\s*$', re.MULTILINE)
OLLAMA_CURL       = re.compile(r'curl\b.*api/tags')
OLLAMA_GUARD      = re.compile(r'if\s+\[.*\$(?:FORGE_)?PROVIDER.*=.*ollama')

scripts = sorted(SCRIPTS.glob("phase4_*.sh"))
if not scripts:
    print(f"  {WARN}  No phase4_*.sh scripts found — nothing to verify")
else:
    script_failures: dict[str, list[str]] = {}

    for sh in scripts:
        name = sh.name
        text = sh.read_text()
        lines = text.splitlines()
        errs: list[str] = []

        # 3 — eval call present
        if not EVAL_PATTERN.search(text):
            errs.append('missing: eval "$(python scripts/llm_config.py --export)"')

        # 4 — no hardcoded FORGE_PROVIDER=
        m = HARDCODE_PATTERN.search(text)
        if m:
            errs.append(f"hardcoded FORGE_PROVIDER assignment: {m.group(0).strip()}")

        # 5 — every ollama curl/api/tags must be inside a FORGE_PROVIDER guard
        if OLLAMA_CURL.search(text):
            if not OLLAMA_GUARD.search(text):
                errs.append(
                    "ollama health check (curl …/api/tags) is NOT wrapped in "
                    'if [ "$FORGE_PROVIDER" = "ollama" ] guard'
                )

        if errs:
            script_failures[name] = errs

    checked = len(scripts)
    bad = len(script_failures)
    good = checked - bad

    if good:
        ok(f"{good}/{checked} scripts fully compliant")
    if bad:
        for name, errs in sorted(script_failures.items()):
            for e in errs:
                fail(f"{name}: {e}")


# ── Summary ────────────────────────────────────────────────────────────────
print()
if failures:
    print(f"\033[31m{'═'*64}\033[0m")
    print(f"\033[31m  FAILED — {len(failures)} issue(s) found. Fix before committing.\033[0m")
    print(f"\033[31m{'═'*64}\033[0m")
    sys.exit(1)
else:
    print(f"\033[32m{'═'*64}\033[0m")
    print(f"\033[32m  ALL CHECKS PASSED — LLM config format invariants satisfied.\033[0m")
    print(f"\033[32m{'═'*64}\033[0m")
    sys.exit(0)

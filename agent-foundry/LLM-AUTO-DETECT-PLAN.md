# LLM Auto-Detection Implementation Plan

## Goal

All 43 agents should automatically use the Claude model when running inside a
Claude Code session, and fall back to Ollama when not. The LLM is defined in
**exactly one place** — `scripts/backend_config.py` — which is already the
centralized config resolver consumed by every runner.

---

## How the System Works Today

```
config.toml  ──►  scripts/backend_config.py (resolve())
                         │
              ┌──────────┴────────────────────────────────────┐
              ▼                                                ▼
agents/common/runners/subagent_runner.py        ...crewai_runner.py
agents/common/runners/claude_sdk_runner.py      ...langgraph_runner.py
              │
              ▼  (all 172 thin dispatchers delegate here)
agents/api-tester/*/subagent|claude_sdk|crewai|langgraph/run.py  (×160)
agents/general/*/subagent|claude_sdk|crewai|langgraph/run.py     (×12)
```

**Nothing in the individual `run.py` files touches the model.** They all call
`build_invoker(WS, system, user_message)` which internally calls
`backend_config.resolve(ws)` to get the active spec.

`.claude/agents/*.md` files use `model: inherit` — Claude Code already picks
the right model for those. No change needed there.

---

## What Needs to Change

**1 file. 1 new function. 3 lines added to an existing function.**

| File | Change type |
|------|-------------|
| `scripts/backend_config.py` | Add `_is_claude_code_session()` + 3-line auto-detect block in `_load_config()` |
| `config.toml` | Comment update only (no functional change) |
| Every other file | **No change required** |

---

## Exact Changes

### File 1 — `scripts/backend_config.py`

**Current file structure (relevant lines):**

```python
Line 27  DEFAULTS = {
Line 28      "provider": "ollama",
...
Line 34  }
Line 35  (blank)
Line 36  (blank)
Line 37  def _load_config(workspace: Path | None = None) -> dict:
Line 38      cfg = dict(DEFAULTS)
Line 39      path = (workspace or Path(".")) / "config.toml"
Line 40      if tomllib and path.exists():
Line 41          with open(path, "rb") as f:
Line 42              data = tomllib.load(f)
Line 43          cfg.update(data.get("backend", {}))
Line 44      # env overrides win (handy for quick experiments)
Line 45      for k in cfg:
Line 46          env = os.environ.get(f"FORGE_{k.upper()}")
Line 47          if env:
Line 48              cfg[k] = env
Line 49      return cfg
```

#### Change A — Insert new function after line 34 (after the closing `}` of DEFAULTS)

**INSERT between lines 34 and 37** (between DEFAULTS and `_load_config`):

```python
def _is_claude_code_session() -> bool:
    """Return True when running inside a Claude Code agent session.

    Detection heuristic: the ``claude`` CLI is on PATH (always true inside
    Claude Code) AND ``ANTHROPIC_API_KEY`` is set (always true when running
    as a Claude Code subagent with API credentials).
    Ollama is the default when neither condition holds.
    """
    import shutil
    return (
        bool(os.environ.get("ANTHROPIC_API_KEY"))
        and shutil.which("claude") is not None
    )
```

#### Change B — Replace `_load_config()` body

**Replace lines 37–49** with:

```python
def _load_config(workspace: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)

    # 1. Static config.toml (lowest priority — sets project-level defaults).
    path = (workspace or Path(".")) / "config.toml"
    if tomllib and path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        cfg.update(data.get("backend", {}))

    # 2. Claude Code session auto-detection (overrides config.toml default).
    #    Skipped when FORGE_PROVIDER is explicitly set so callers can still
    #    force a specific backend (e.g. FORGE_PROVIDER=ollama in CI).
    if not os.environ.get("FORGE_PROVIDER") and _is_claude_code_session():
        cfg["provider"] = "claude-haiku"

    # 3. Explicit env overrides win (handy for quick experiments / CI).
    for k in cfg:
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env

    return cfg
```

**Unified diff:**
```diff
+def _is_claude_code_session() -> bool:
+    """Return True when running inside a Claude Code agent session.
+
+    Detection heuristic: the ``claude`` CLI is on PATH (always true inside
+    Claude Code) AND ``ANTHROPIC_API_KEY`` is set (always true when running
+    as a Claude Code subagent with API credentials).
+    Ollama is the default when neither condition holds.
+    """
+    import shutil
+    return (
+        bool(os.environ.get("ANTHROPIC_API_KEY"))
+        and shutil.which("claude") is not None
+    )
+
+
 def _load_config(workspace: Path | None = None) -> dict:
     cfg = dict(DEFAULTS)
-    path = (workspace or Path(".")) / "config.toml"
+
+    # 1. Static config.toml (lowest priority — sets project-level defaults).
+    path = (workspace or Path(".")) / "config.toml"
     if tomllib and path.exists():
         with open(path, "rb") as f:
             data = tomllib.load(f)
         cfg.update(data.get("backend", {}))
-    # env overrides win (handy for quick experiments)
+
+    # 2. Claude Code session auto-detection (overrides config.toml default).
+    #    Skipped when FORGE_PROVIDER is explicitly set so callers can still
+    #    force a specific backend (e.g. FORGE_PROVIDER=ollama in CI).
+    if not os.environ.get("FORGE_PROVIDER") and _is_claude_code_session():
+        cfg["provider"] = "claude-haiku"
+
+    # 3. Explicit env overrides win (handy for quick experiments / CI).
     for k in cfg:
         env = os.environ.get(f"FORGE_{k.upper()}")
         if env:
             cfg[k] = env
     return cfg
```

---

### File 2 — `config.toml` (comment update only, no functional change)

**Replace lines 3–14** (the header comment block in `[backend]`) with:

```toml
[backend]
# provider: controls the LLM backend for every runner in the foundry.
#
# Values:
#   "ollama"       — local / air-gapped (default when not in Claude Code)
#   "claude-haiku" — Anthropic claude-haiku-4-5 via API key
#   "claude-cli"   — Anthropic via the `claude -p` CLI shim (no API credits)
#
# AUTO-DETECTION: scripts/backend_config.py automatically detects Claude Code
# sessions (ANTHROPIC_API_KEY set + `claude` CLI on PATH) and switches to
# "claude-haiku" without touching this file.
#
# To override auto-detection:
#   FORGE_PROVIDER=ollama        force Ollama even inside Claude Code
#   FORGE_PROVIDER=claude-haiku  force Claude even outside Claude Code
#
# The value below is the fallback when NOT in a Claude Code session.
```

---

## Verification: Every Agent Accounted For

### `.claude/agents/` — 2 files (Claude Code native subagents)

| File | `model:` line | Action |
|------|--------------|--------|
| `api-tester-test-idempotency-of-endpoints.md` | `model: inherit` (line 5) | **No change** — inherits Claude Code's active model |
| `api-tester-validate-correlation-id-propagation.md` | `model: inherit` (line 5) | **No change** — inherits Claude Code's active model |

`model: inherit` is correct for Claude Code subagents. ✅

### `agents/common/runners/` — 4 shared runner files

All already call `backend_config.resolve(ws)` and branch on
`spec["native"]["kind"]`. After the `backend_config.py` change, when in a
Claude Code session `spec["native"]` becomes `{"kind": "anthropic", "model": "claude-haiku-4-5"}`,
which triggers the Anthropic path in every runner automatically.

| File | Branching logic | Claude Code result |
|------|----------------|-------------------|
| `subagent_runner.py` | `if kind != "anthropic" or not which("claude")` → skip native | Uses `claude -p` ✅ |
| `claude_sdk_runner.py` | `if kind == "anthropic"` → `claude_agent_sdk` | Uses Claude SDK ✅ |
| `crewai_runner.py` | `if kind == "anthropic"` → `LLM(model="anthropic/claude-haiku-4-5")` | Uses Anthropic ✅ |
| `langgraph_runner.py` | `if kind == "anthropic"` → `ChatAnthropic` | Uses Anthropic ✅ |

**No changes needed in any runner file.**

### `agents/api-tester/*/` — 40 agents × 4 runners = 160 `run.py` files

Every file is a thin dispatcher. None reference a model directly. All delegate
to the runner → `backend_config`. **No changes needed.**

Full list of agents covered:
```
validate-request-payloads           verify-response-status-codes
test-authentication-flows           check-authorization-rules
validate-json-schema-responses      test-pagination-behavior
verify-error-message-clarity        test-rate-limit-enforcement
validate-query-parameter-handling   test-idempotency-of-endpoints
verify-content-type-negotiation     validate-null-empty-fields
test-timeout-handling               verify-crud-operation-integrity
test-concurrent-request-handling    validate-header-propagation
test-webhook-delivery               run-regression-suite
track-defect-density                validate-api-versioning-behavior
test-ssl-tls-enforcement            verify-caching-headers
validate-correlation-id-propagation test-bulk-operation-endpoints
verify-audit-log-generation         validate-search-and-filter-queries
test-file-upload-and-download       verify-sorting-behavior
test-event-driven-api-triggers      test-ip-allowlist-enforcement
test-api-gateway-routing            verify-third-party-oauth-integration
test-multipart-form-data-handling   validate-retry-after-header-compliance
test-soft-delete-behavior           validate-graphql-depth-limits
test-long-polling-support           verify-enum-value-restrictions
measure-api-consumer-satisfaction   create-postman-collection
```

### `agents/general/*/` — 3 agents × 4 runners = 12 `run.py` files

Same pattern as api-tester. **No changes needed.**
```
test-case-creator    run-cicd-pipeline    bug-reporter
```

### `agents/*/subagent/*.md` — 43 system-prompt files

Loaded as plain strings by `runners/utils.py → load_system_prompt()`.
Contain agent instructions only, no LLM config. **No changes needed.**

---

## Priority / Override Ladder After Change

```
Priority    Mechanism                        Example
────────────────────────────────────────────────────────────────────────────
  1 (HIGH)  FORGE_PROVIDER env var           FORGE_PROVIDER=ollama
  2         Claude Code auto-detection       ANTHROPIC_API_KEY + claude CLI
  3         config.toml [backend].provider   provider = "ollama"
  4 (LOW)   DEFAULTS                         "ollama" (hardcoded in .py)
```

---

## Complete Replacement for `scripts/backend_config.py`

```python
#!/usr/bin/env python3
"""
Central backend switch for every component (agents, judge, debaters, evolvers).

One provider toggle drives the whole foundry. Swapping models is a one-line
change in config.toml ([backend].provider). Two first-class providers:

    - "ollama"        : local, OpenAI-compatible at http://127.0.0.1:11434/v1
    - "claude-haiku"  : Anthropic claude-haiku-4-5

AUTO-DETECTION: when ANTHROPIC_API_KEY is set and the ``claude`` CLI is on PATH
(both true inside a Claude Code session), the provider is automatically set to
"claude-haiku" so every runner uses Anthropic without any config change.
Override with FORGE_PROVIDER=ollama to force local even inside Claude Code.

Components that only speak the OpenAI protocol (SkillClaw, EverOS's OpenAI path)
reach Claude through a local LiteLLM proxy, so Claude stays interchangeable
everywhere. Ollama is natively OpenAI-compatible and needs no shim.

stdlib only. Reads config.toml if present (Py3.11+ tomllib), else env vars,
else sane local defaults.
"""
from __future__ import annotations
import os
from pathlib import Path

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

DEFAULTS = {
    "provider": "ollama",
    "ollama_base_url": "http://127.0.0.1:11434/v1",
    "ollama_model": "qwen2.5:14b-instruct",
    "claude_model": "claude-haiku-4-5",
    "litellm_proxy_url": "http://127.0.0.1:4000/v1",  # universal OpenAI-compat shim
    "claude_cli_shim_url": "http://127.0.0.1:8787/v1",  # OpenAI-compat shim over `claude -p`
}


def _is_claude_code_session() -> bool:
    """Return True when running inside a Claude Code agent session.

    Detection heuristic: the ``claude`` CLI is on PATH (always true inside
    Claude Code) AND ``ANTHROPIC_API_KEY`` is set (always true when running
    as a Claude Code subagent with API credentials).
    Ollama is the default when neither condition holds.
    """
    import shutil
    return (
        bool(os.environ.get("ANTHROPIC_API_KEY"))
        and shutil.which("claude") is not None
    )


def _load_config(workspace: Path | None = None) -> dict:
    cfg = dict(DEFAULTS)

    # 1. Static config.toml (lowest priority — sets project-level defaults).
    path = (workspace or Path(".")) / "config.toml"
    if tomllib and path.exists():
        with open(path, "rb") as f:
            data = tomllib.load(f)
        cfg.update(data.get("backend", {}))

    # 2. Claude Code session auto-detection (overrides config.toml default).
    #    Skipped when FORGE_PROVIDER is explicitly set so callers can still
    #    force a specific backend (e.g. FORGE_PROVIDER=ollama in CI).
    if not os.environ.get("FORGE_PROVIDER") and _is_claude_code_session():
        cfg["provider"] = "claude-haiku"

    # 3. Explicit env overrides win (handy for quick experiments / CI).
    for k in cfg:
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env

    return cfg


def resolve(workspace: Path | None = None) -> dict:
    """Return a uniform connection spec all components can consume.

    Always exposes an OpenAI-compatible (base_url, model, api_key_env) tuple,
    plus the native flavor when relevant, so each component can pick the path
    it supports without any component hardcoding a model.
    """
    cfg = _load_config(workspace)
    provider = cfg["provider"]

    if provider == "ollama":
        return {
            "provider": "ollama",
            "openai_compatible": True,
            "base_url": cfg["ollama_base_url"],
            "model": cfg["ollama_model"],
            "api_key_env": "OLLAMA_API_KEY",  # ollama ignores it; placeholder ok
            "native": {"kind": "ollama", "model": cfg["ollama_model"]},
            "air_gapped": True,
        }

    if provider == "claude-haiku":
        return {
            "provider": "claude-haiku",
            # OpenAI-compatible path = via the local LiteLLM proxy (for SkillClaw/EverOS)
            "openai_compatible": True,
            "base_url": cfg["litellm_proxy_url"],
            "model": cfg["claude_model"],
            "api_key_env": "ANTHROPIC_API_KEY",
            # native path = direct Anthropic (for LangGraph/CrewAI/SkillOpt/SDK)
            "native": {"kind": "anthropic", "model": cfg["claude_model"]},
            "air_gapped": False,  # cloud backend; opt-in only
        }

    if provider == "claude-cli":
        # Claude via the claude.ai subscription, exposed behind an OpenAI-compatible
        # shim over `claude -p` (scripts/claude_cli_shim.py). Used when ANTHROPIC_API_KEY
        # has no credits but the subscription works. Every framework reaches it through
        # its OpenAI-compatible code path. Native kind "openai-cli" tells the runners to
        # use the OpenAI client / a direct `claude -p` call rather than the SDK paths.
        return {
            "provider": "claude-cli",
            "openai_compatible": True,
            "base_url": cfg["claude_cli_shim_url"],
            "model": cfg["claude_model"],
            "api_key_env": "FORGE_SHIM_KEY",   # any non-empty string; the shim ignores it
            "native": {"kind": "openai-cli", "model": cfg["claude_model"]},
            "air_gapped": False,
        }

    raise ValueError(
        f"Unknown backend provider {provider!r}. "
        f"Use 'ollama', 'claude-haiku', or 'claude-cli' in config.toml [backend].provider."
    )


if __name__ == "__main__":
    import json
    print(json.dumps(resolve(), indent=2))
```

---

## Quick Smoke Test

```bash
# Inside Claude Code (ANTHROPIC_API_KEY set, claude on PATH):
python scripts/backend_config.py
# → "provider": "claude-haiku", "native": {"kind": "anthropic", ...}

# Force Ollama even inside Claude Code:
FORGE_PROVIDER=ollama python scripts/backend_config.py
# → "provider": "ollama"

# Simulate non-Claude Code environment:
env -u ANTHROPIC_API_KEY python scripts/backend_config.py
# → "provider": "ollama" (falls to config.toml / DEFAULTS)
```

# LLM Provider Auto-Detection — Implementation Plan

**Goal:** One central location defines the LLM used by all agents. When running inside a
Claude Code session the foundry automatically uses `claude-haiku-4-5`. When not in a Claude
Code session it falls back to Ollama. No agent file carries its own model setting.

---

## Current State

| Location | Count | Current model field |
|---|---|---|
| `.claude/agents/*.md` | 2 | `model: inherit` ✅ no change needed |
| `agents/*/subagent/*.md` | 43 | `model: inherit` ✅ no change needed |
| `config.toml` line 14 | 1 | `provider = "ollama"` ← **change this** |
| `scripts/phase4_idempotency_run.sh` line 22 | 1 | `export FORGE_PROVIDER="ollama"` ← **remove** |
| All other `scripts/phase4_*.sh` (45 files) | 45 | no FORGE_PROVIDER set, but start ollama unconditionally ← **guard** |

All 45 agent `.md` files already use `model: inherit`. They will not be touched.
The single source of truth lives in two places that act together:
`config.toml` (declarative default) + `scripts/llm_config.py` (runtime resolver).

---

## Files to Create

### `scripts/llm_config.py` ← **NEW — the single resolver**

Create this file. It is the only place in the entire repo that decides which LLM is used.

```python
#!/usr/bin/env python3
"""
Forge LLM Config — single source of truth for provider resolution.

Priority (highest → lowest):
  1. FORGE_PROVIDER env var (explicit override, useful for CI or one-off runs)
  2. config.toml [backend].provider (if not "auto")
  3. Auto-detect: CLAUDE_CODE_ENTRYPOINT is set → claude-haiku
                  otherwise                     → ollama

Usage:
    python scripts/llm_config.py          # prints JSON to stdout
    python scripts/llm_config.py --export # prints eval-able bash exports
"""
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

try:
    import tomllib          # Python 3.11+
except ImportError:
    try:
        import tomli as tomllib   # pip install tomli
    except ImportError:
        sys.exit("llm_config.py requires tomllib (Python 3.11+) or tomli (pip install tomli)")

FOUNDRY_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = FOUNDRY_ROOT / "config.toml"


def _is_claude_code_session() -> bool:
    """
    Return True when this process is running inside a Claude Code agent session.

    Claude Code sets CLAUDE_CODE_ENTRYPOINT automatically when it spawns any
    agent subprocess (cli, vscode, sub-agent, etc.). That is the canonical signal.
    ANTHROPIC_API_KEY is a secondary check for cases where the key is present
    but the entrypoint var is not (e.g. raw `claude -p` invocations).
    """
    return bool(os.environ.get("CLAUDE_CODE_ENTRYPOINT")) or bool(
        os.environ.get("ANTHROPIC_API_KEY")
    )


def resolve() -> dict:
    """
    Resolve the active LLM backend.

    Returns a dict with keys: provider, model, base_url, api_key_env
    """
    cfg = tomllib.loads(CONFIG_PATH.read_text())
    backend = cfg.get("backend", {})

    # Priority 1: explicit env override
    provider = os.environ.get("FORGE_PROVIDER", "").strip()

    # Priority 2: config.toml
    if not provider:
        provider = backend.get("provider", "auto")

    # Priority 3: auto-detect
    if provider == "auto":
        provider = "claude-haiku" if _is_claude_code_session() else "ollama"

    if provider == "ollama":
        return {
            "provider": "ollama",
            "model": backend.get("ollama_model", "qwen2.5:14b-instruct"),
            "base_url": backend.get("ollama_base_url", "http://127.0.0.1:11434/v1"),
            "api_key_env": None,
        }

    if provider in ("claude-haiku", "claude"):
        return {
            "provider": "claude-haiku",
            "model": backend.get("claude_model", "claude-haiku-4-5"),
            "base_url": backend.get("litellm_proxy_url", "http://127.0.0.1:4000/v1"),
            "api_key_env": "ANTHROPIC_API_KEY",
        }

    raise ValueError(
        f"Unknown provider {provider!r}. Valid values: ollama, claude-haiku, auto"
    )


def _bash_exports(cfg: dict) -> str:
    lines = [
        f'export FORGE_PROVIDER="{cfg["provider"]}"',
        f'export FORGE_MODEL="{cfg["model"]}"',
        f'export FORGE_BASE_URL="{cfg["base_url"]}"',
    ]
    if cfg["api_key_env"]:
        lines.append(f'# FORGE_API_KEY_ENV="{cfg["api_key_env"]}"')
    return "\n".join(lines)


if __name__ == "__main__":
    cfg = resolve()
    if "--export" in sys.argv:
        print(_bash_exports(cfg))
    else:
        print(json.dumps(cfg, indent=2))
```

---

## Files to Modify

### 1. `config.toml`

**Line 14 only.**

```toml
# BEFORE
provider = "ollama"

# AFTER
provider = "auto"
```

`"auto"` tells `llm_config.py` to detect at runtime. To pin permanently, set it back to
`"ollama"` or `"claude-haiku"`. To override for one run, use `FORGE_PROVIDER=ollama bash scripts/...`.

---

### 2. Shell scripts — two patterns

Every `scripts/phase4_*.sh` file falls into one of two patterns. Find which pattern
each file uses and apply the matching patch.

---

#### Pattern A — scripts that explicitly hardcode `export FORGE_PROVIDER="ollama"`

**Matches:** `scripts/phase4_idempotency_run.sh` (line 22)

**Step 1 — Remove the hardcoded line:**
```bash
# DELETE this line:
export FORGE_PROVIDER="ollama"                 # <-- local Ollama backend
```

**Step 2 — Add the detection block immediately after `cd "$FOUNDRY"`:**
```bash
# ── LLM provider (single source: scripts/llm_config.py) ─────────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ─────────────────────────────────────────────────────────────────────────────
```

**Step 3 — Wrap the ollama health-check in a provider guard:**
```bash
# BEFORE:
if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
  echo "FATAL: Ollama is not running at $OLLAMA_URL. Start it yourself ..."
  exit 3
fi

# AFTER:
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${FORGE_OLLAMA_URL:-http://127.0.0.1:11434}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not running. Start it ('ollama serve'), pull the model, then re-run."
    echo "       Or run inside a Claude Code session to use claude-haiku automatically."
    exit 3
  fi
fi
```

---

#### Pattern B — scripts that do NOT set FORGE_PROVIDER but start ollama unconditionally

**Matches:** all other `phase4_*.sh` files (45 files):
`phase4_run.sh`, `phase4_authz.sh`, `phase4_pagination_run.sh`, `phase4_run_auth.sh`,
`phase4_schema_run.sh`, `phase4_webhook_run.sh`, `phase4_defectdensity_run.sh`,
`phase4_ip_allowlist_run.sh`, `phase4_ratelimit_run.sh`, `phase4_searchfilter_run.sh`,
`phase4_queryparam_run.sh`, `phase4_clarity_run.sh`, `phase4_concurrency_run.sh`,
`phase4_header_run.sh`, `phase4_crud_run.sh`, `phase4_cn_run.sh`,
`phase4_versioning_run.sh`, `phase4_tls_run.sh`, `phase4_regression_run.sh`,
`phase4_caching_run.sh`, `phase4_sorting_run.sh`, `phase4_auditlog_run.sh`,
`phase4_cid_run.sh`, `phase4_eventdriven_run.sh`, `phase4_bulk_run.sh`,
`phase4_null_run.sh`, `phase4_upload_run.sh`, `phase4_routing_run.sh`,
`phase4_oauth_run.sh`, `phase4_multipart_run.sh`, `phase4_timeout_run.sh`,
`phase4_retryafter_run.sh`, `phase4_nps_run.sh`, `phase4_gqldepth_run.sh`,
`phase4_longpoll_run.sh`, `phase4_softdelete_run.sh`, `phase4_enum_run.sh`,
`phase4_cicd_run.sh`, `phase4_postman_run.sh`, `phase4_testcase_run.sh`,
`phase4_bugreport_run.sh`

**Step 1 — Add the detection block immediately after `cd "$FOUNDRY"`:**
```bash
# ── LLM provider (single source: scripts/llm_config.py) ─────────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ─────────────────────────────────────────────────────────────────────────────
```

**Step 2 — Wrap the unconditional ollama startup block:**
```bash
# BEFORE (the existing ollama startup block, usually labelled "# 1. Ollama up"):
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  say "starting ollama"; nohup ollama serve >/tmp/ollama.log 2>&1 &
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
fi

# AFTER:
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    say "starting ollama"; nohup ollama serve >/tmp/ollama.log 2>&1 &
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
  fi
fi
```

---

### 3. Python `run_*.py` scripts — NO CHANGES

`scripts/run_agents.py`, `scripts/run_idempotency_agents.py`, and all other Python
orchestrators pass `env = dict(os.environ)` to each subprocess. Because the shell
script runs `eval "$(python scripts/llm_config.py --export)"` first, `FORGE_PROVIDER`,
`FORGE_MODEL`, and `FORGE_BASE_URL` are already exported before Python launches.
No edits needed.

---

## Complete Change Summary

| Action | File | Exact change |
|---|---|---|
| **CREATE** | `scripts/llm_config.py` | Full content listed above |
| **MODIFY** | `config.toml` | Line 14: `"ollama"` → `"auto"` |
| **MODIFY** | `scripts/phase4_idempotency_run.sh` | Pattern A: remove line 22, add detection block, guard health-check |
| **MODIFY** | `scripts/phase4_run.sh` | Pattern B: add detection block, wrap ollama start |
| **MODIFY** | `scripts/phase4_authz.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_pagination_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_run_auth.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_schema_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_webhook_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_defectdensity_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_ip_allowlist_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_ratelimit_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_searchfilter_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_queryparam_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_clarity_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_concurrency_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_header_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_crud_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_cn_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_versioning_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_tls_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_regression_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_caching_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_sorting_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_auditlog_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_cid_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_eventdriven_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_bulk_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_null_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_upload_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_routing_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_oauth_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_multipart_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_timeout_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_retryafter_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_nps_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_gqldepth_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_longpoll_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_softdelete_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_enum_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_cicd_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_postman_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_testcase_run.sh` | Pattern B |
| **MODIFY** | `scripts/phase4_bugreport_run.sh` | Pattern B |
| **NO CHANGE** | `.claude/agents/api-tester-test-idempotency-of-endpoints.md` | `model: inherit` ✅ |
| **NO CHANGE** | `.claude/agents/api-tester-validate-correlation-id-propagation.md` | `model: inherit` ✅ |
| **NO CHANGE** | `agents/api-tester/*/subagent/*.md` (40 files) | `model: inherit` ✅ |
| **NO CHANGE** | `agents/general/*/subagent/*.md` (3 files) | `model: inherit` ✅ |
| **NO CHANGE** | `scripts/run_agents.py` | Inherits env from shell ✅ |
| **NO CHANGE** | `scripts/run_idempotency_agents.py` | Inherits env from shell ✅ |
| **NO CHANGE** | All other `scripts/run_*.py` | Inherits env from shell ✅ |

---

## How the Detection Logic Works

```
Shell script runs: eval "$(python scripts/llm_config.py --export)"
                                        │
                             llm_config.resolve()
                                        │
               ┌────────────────────────┼──────────────────────────┐
          Priority 1               Priority 2                 Priority 3
       FORGE_PROVIDER           config.toml                  auto-detect
        env var set?            provider = ?            (when provider="auto")
               │                        │                          │
              yes                 not "auto"               CLAUDE_CODE_ENTRYPOINT
               │                        │                     env var set?
               ▼                        ▼                          │
         use that value           use that value          yes ─────┴───── no
                                                           │               │
                                                     claude-haiku        ollama
```

`CLAUDE_CODE_ENTRYPOINT` is the environment variable Claude Code sets automatically
whenever it spawns any agent subprocess. It is always present inside a Claude Code
session and never present in a plain shell run.

---

## Verification

After implementing, test all three paths:

```bash
# 1. Auto-detects as claude-haiku inside a Claude Code session (CLAUDE_CODE_ENTRYPOINT is set)
python scripts/llm_config.py

# 2. Auto-detects as ollama in a plain shell with no API key
ANTHROPIC_API_KEY="" CLAUDE_CODE_ENTRYPOINT="" python scripts/llm_config.py

# 3. FORGE_PROVIDER override wins regardless of session
FORGE_PROVIDER=ollama python scripts/llm_config.py
FORGE_PROVIDER=claude-haiku python scripts/llm_config.py

# 4. Check the bash export form (used by shell scripts)
python scripts/llm_config.py --export
```

---

## Override Quick Reference

| Intent | How |
|---|---|
| Force ollama for one run | `FORGE_PROVIDER=ollama bash scripts/phase4_idempotency_run.sh` |
| Force claude-haiku for one run | `FORGE_PROVIDER=claude-haiku bash scripts/phase4_run.sh` |
| Pin the permanent default to ollama | `config.toml` line 14 → `provider = "ollama"` |
| Pin the permanent default to claude-haiku | `config.toml` line 14 → `provider = "claude-haiku"` |
| Restore auto-detection (recommended) | `config.toml` line 14 → `provider = "auto"` |

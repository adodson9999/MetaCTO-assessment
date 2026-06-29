# Backend policy — use the Claude Code session first, Ollama only as fallback

(Supersedes the old `Need_Ollama` note. Ollama is no longer the default — it's the fallback.)

## Policy
The agent-foundry LLM backend is chosen by `agent-foundry/scripts/backend_config.py` (and
`llm_config.py`). `agent-foundry/config.toml` sets `provider = "auto"`, which resolves as:

- **Inside a Claude Code session** → use **Claude** (the session you're on), in this order of
  the first one that's actually reachable: `claude-cli` → `claude-haiku` → `ollama`.
- **Not in a Claude Code session** (or `FORGE_PROVIDER=ollama`) → use **Ollama**.

So when you're working in Claude Code, the foundry should run on **Claude**, not the local
14B. Ollama is only the air-gapped / no-session fallback, or when you explicitly ask for it.

## Why a shim is needed for the session
`auto` only selects `claude-cli` if its OpenAI-compatible endpoint is **listening**. That
endpoint is a tiny local shim (`scripts/claude_cli_shim.py`) over the `claude -p` CLI — it
uses your **Claude subscription** (no `ANTHROPIC_API_KEY` / no API credits). If the shim is
down, `auto` falls through to `claude-haiku` (needs the LiteLLM proxy on :4000) and finally
to Ollama. **Start the shim and `auto` uses your session automatically.**

## Use the Claude Code session (one command)
```bash
cd /Users/alexdodson/Downloads/Jarvis/assessment/MetaCTO-Assessment
# bring up the session backend (claude -p shim on :8787); model: sonnet (reliable for the
# documentation-reviewer; use --model opus or haiku if you prefer)
agent-foundry/scripts/use-claude-session.sh        # starts the shim + verifies + prints resolved backend
```
Then run anything WITHOUT forcing ollama — `auto` will pick `claude-cli`:
```bash
FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  agent-foundry/.venv/bin/python agent-foundry/scripts/<driver>.py <RUN_ID>     # provider=auto -> claude-cli
# or pin it explicitly:
FORGE_PROVIDER=claude-cli FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  agent-foundry/.venv/bin/python agent-foundry/scripts/<driver>.py <RUN_ID>
```

### Status checks
```bash
curl -s http://127.0.0.1:8787/v1/models                       # claude-cli shim up?
FORGE_WORKSPACE="$(pwd)/agent-foundry" agent-foundry/.venv/bin/python agent-foundry/scripts/backend_config.py   # what 'auto' resolves to
```

## Ollama (fallback only — not in a session, air-gapped, or explicitly requested)
```bash
ollama serve &                                  # daemon (qwen2.5:14b-instruct, ~9 GB pulled)
FORGE_PROVIDER=ollama FORGE_WORKSPACE="$(pwd)/agent-foundry" \
  agent-foundry/.venv/bin/python agent-foundry/scripts/<driver>.py <RUN_ID>
```
Note: the local 14B is NOT reliable for the documentation-reviewer (it returns invalid
verdicts on arbitrary inputs) — use the Claude session for bug adjudication.

## Local API target (unchanged, separate from the LLM backend)
The test target is still the local DummyJSON node on :8899:
```bash
JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development PORT=8899 LOG_ENABLED=false node index.js &
```

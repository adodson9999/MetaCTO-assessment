# Backends — provider resolution

One central config (`scripts/backend_config.py` + `config.toml`) resolved by
`scripts/llm_config.py`. **Never hardcode a provider** (constitution Article I.7,
Article VI). `config.toml [backend].provider` is always `"auto"`.

## Resolution order

`auto` resolves in this order, first available wins:

1. **Current Claude Code session** (default). If the skill is running inside a
   connected Claude Code session, use that session's model. This is the default
   for the build, the agents, the judge, the debaters, the determinism checker,
   the golden suite, and the evolvers.
2. **Ollama** (local fallback). If there is no connected session, use the local
   Ollama model in `config.toml [backend.ollama].model`. Fully air-gapped.
3. **Explicit cloud** (opt-in only). e.g. `claude-haiku-4-5` — used only when the
   user explicitly sets `[backend].allow_cloud = true` and selects it.

`FORGE_PROVIDER` is exported once, by `eval "$(python scripts/llm_config.py --export)"`,
and every script reads it from there. Ollama health-checks are wrapped in
`if [ "$FORGE_PROVIDER" = "ollama" ]; then … fi`. After editing any shell script,
run `python scripts/verify_llm_config.py` (must exit 0).

## The LiteLLM shim

A LiteLLM proxy provides one OpenAI-compatible endpoint so components that speak
the OpenAI API (SkillClaw, EverOS's OpenAI path) work against whichever provider
is resolved — session, Ollama, or cloud. Swapping the model is a one-line change
inherited everywhere.

## `llm_config.py --export` contract

```
$ python scripts/llm_config.py --export
export FORGE_PROVIDER="session"          # or "ollama" / "claude-haiku"
export FORGE_MODEL="<resolved-model-id>"
export FORGE_OPENAI_BASE="http://127.0.0.1:<litellm-port>/v1"
```

Detection: `session` is selected when a Claude Code session environment is present
(the resolver probes for it); otherwise it probes `OLLAMA_HOST`/default
`127.0.0.1:11434`; otherwise, if `allow_cloud`, the configured cloud model.

# Forge Agents — one-command setup (Windows / PowerShell).
# Idempotent. Local-first; cloud (Claude Haiku) is opt-in.
$ErrorActionPreference = "Stop"
function Say($m){ Write-Host "▸ $m" -ForegroundColor Cyan }
function Warn($m){ Write-Host "! $m" -ForegroundColor Yellow }

$Here = Split-Path -Parent $MyInvocation.MyCommand.Definition
Set-Location $Here

Say "Checking Python and uv"
if (-not (Get-Command python -ErrorAction SilentlyContinue)) { Warn "Python not found"; exit 1 }
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  Warn "uv not found — installing"
  powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
}

Say "Installing foundry Python deps"
uv venv .venv 2>$null
. .\.venv\Scripts\Activate.ps1
uv pip install --quiet langgraph langchain langchain-community langchain-anthropic crewai litellm claude-agent-sdk sentence-transformers pyyaml

if (Get-Command ollama -ErrorAction SilentlyContinue) {
  Say "Ollama present — pulling default local model"
  ollama pull qwen2.5:14b-instruct
} else {
  Warn "Ollama not found. Install from https://ollama.com for fully air-gapped runs,"
  Warn "or set [backend].provider = 'claude-haiku' in config.toml (cloud, opt-in)."
}

Say "For the Claude path through SkillClaw/EverOS, run a LiteLLM proxy:"
Write-Host "    litellm --model claude-haiku-4-5 --port 4000"

if (Test-Path vendor/EverOS) {
  Say "EverOS vendored — init + start bound to 127.0.0.1"
  Write-Host "    cd vendor/EverOS; uv sync; everos init; everos server start"
} else {
  Warn "EverOS not vendored yet — run /scan-and-integrate first."
}

Say "Setup complete. Next: /scan-and-integrate, then /forge-agents."

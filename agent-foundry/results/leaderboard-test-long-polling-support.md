# Leaderboard — longpoll_test_fidelity (higher_is_better)

_No real ranking yet._ The four agents are wired to the **ollama** backend (owner note). This
build never starts the Ollama server — start it yourself (`ollama serve`, with the configured
model `qwen2.5:14b-instruct` pulled), then run `bash scripts/phase4_longpoll_run.sh` for the real
leaderboard. Until Ollama is reachable the script stops early (it does not launch the server).

The build itself is validated deterministically (no LLM):

- reference plan → **100%** Long-Poll-Test Fidelity (reproduces every gold token)
- degraded plan (event case dropped on one channel) → **83.33%** (metric discriminates)
- headline **Long-Poll Response Accuracy = 66.67%** (4/6 cases; `inventory` non-compliant — the QA finding)

Each run appends and keeps best-so-far per agent.

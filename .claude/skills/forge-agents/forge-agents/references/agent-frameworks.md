# Building the Four Agents

All four implement the **same task** and are **built to be measured**: each must emit its metric as JSON to `results/runs/<run-id>/<agent>.json`. The metric schema is defined by the judge (`judge/<group>/<agent-short-name>/metric.json`, e.g. `judge/api-tester/create-postman-collection/metric.json`); every agent emits the same fields so the judge can compare them directly.

Each agent's instruction lines come from the debate gate (`references/debate-gate.md`) — author them there first, then write the approved prompt into the agent's `subagent/<agent-name>.md` file. Each framework gets a **thin dispatcher** `run.py` that delegates all boilerplate to the shared runner.

## Shared contract (all four)

Every agent must:
1. Read the task from `task_spec.md` and the metric contract from `judge/<group>/<agent-short-name>/metric.json` (e.g. `judge/api-tester/create-postman-collection/metric.json`).
2. Use the central backend (`scripts/backend_config.py`) — never hardcode a model.
3. Read/write only inside the workspace sandbox.
4. Share memory via EverOS using the common `project_id`/`app_id` and its own `agent_id`.
5. On completion, write `results/runs/<run-id>/<agent>.json` with at least:
   ```json
   {"agent": "<name>", "run_id": "<id>", "metric_name": "<from judge>",
    "metric_value": <number>, "raw_output_path": "<path>", "ts": "<iso8601>"}
   ```

## Centralized runner architecture

All framework boilerplate lives in `agents/common/runners/`. Each runner exposes one function:

```python
build_invoker(ws, system, user_message_fn, **kwargs) -> Callable[[str], str]
```

`build_invoker` wires up the backend config, constructs the framework-specific model/agent/crew, and returns a single callable `invoke(brief: str) -> str`. Every `run.py` is a **thin dispatcher** that calls `build_invoker` and then wraps `invoke` in the harness's `generate` function.

## Thin dispatcher pattern

Every framework `run.py` follows this structure:

```python
#!/usr/bin/env python3
"""Thin dispatcher: <framework> runner for <agent-name>.

Delegates all framework boilerplate to common/runners/<framework>_runner.py.
"""
from __future__ import annotations
import os, sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[4])))
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

import <harness>                                          # noqa: E402
from <harness>_prompt import active_prompt, user_message  # noqa: E402
from runners.utils import load_system_prompt              # noqa: E402
from runners.<framework>_runner import build_invoker      # noqa: E402

AGENT = "<framework>"   # or "<agent-name>" for subagent
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "<agent-name>.md"


def main() -> None:
    system = load_system_prompt(SUBAGENT_MD, active_prompt)
    invoke = build_invoker(WS, system, user_message)

    def generate(<input>) -> dict:
        # build brief, call invoke, extract result
        return <harness>.extract_json(invoke(brief)) or {}

    summary = <harness>.run_<task>_test(AGENT, generate)
    print(f"[{AGENT}] ...")


if __name__ == "__main__":
    main()
```

The subagent dispatcher omits `active_prompt` (the system prompt comes entirely from `<agent-name>.md`):

```python
system = load_system_prompt(SUBAGENT_MD)   # no primary_fn
```

## LangGraph (`agents/<agent-name>/langgraph/run.py`)

Thin dispatcher → `agents/common/runners/langgraph_runner.py`. The runner builds a `StateGraph` whose nodes carry out the task, selects the model via `backend_config`, and returns the `invoke` callable. AGENT string: `"langgraph"`.

## CrewAI (`agents/<agent-name>/crewai/run.py`)

Thin dispatcher → `agents/common/runners/crewai_runner.py`. The runner builds a `Crew` with the task as one or more `Task`s, routing models through LiteLLM via backend config. AGENT string: `"crewai"`.

## Claude Agent SDK (`agents/<agent-name>/claude_sdk/run.py`)

Thin dispatcher → `agents/common/runners/claude_sdk_runner.py`. The runner selects between the native Claude Agent SDK path (anthropic backend) and the OpenAI-compatible LiteLLM shim (ollama backend). AGENT string: `"claude_sdk"`.

## Claude Code subagent (`agents/<agent-name>/subagent/`)

Two files:

**`<agent-name>.md`** — the canonical agent artifact: YAML frontmatter (`name`, `description`, `tools`, `model`) plus the debate-gated system prompt as the body. This is the only file that contains the agent's instructions; it is also the file the debate gate writes to directly.

**`run.py`** — thin dispatcher → `agents/common/runners/subagent_runner.py`. The runner reads the system prompt from `<agent-name>.md`, drives the agent via the `claude` CLI (when the backend is anthropic and `FORGE_USE_CLAUDE_AGENT_SDK` is set) or via the OpenAI-compatible local endpoint (ollama), and returns the `invoke` callable. AGENT string: `"<agent-name>"` (the full agent name, not `"subagent"`).

**Where the subagent file lives.** The canonical artifact is at `agents/<agent-name>/subagent/<agent-name>.md`. For Claude Code to discover it as a Task-tool subagent, register it at the host repository's `.claude/agents/<agent-name>.md` — create that file as a relative symlink to the canonical artifact so there is a single source of truth. The subagent's `name:` frontmatter, its filename, the symlink name, and `run.py`'s `SUBAGENT_MD` path must all match.

## Why four-of-the-same

The point is a controlled comparison: identical task, identical metric, four framework substrates. Differences in the leaderboard are attributable to the framework (and its evolved skills), not to the task. Both Claude variants are scored separately so the user can see which Claude flavor wins too.

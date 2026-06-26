"""Shared CrewAI runner — Agent + Task + Crew boilerplate.

Thin dispatchers call::

    from runners.crewai_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw crew output)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
    role: str = "API testing agent",
    goal: str = "Analyse the given brief and produce a JSON test plan per your system instructions.",
    expected_output: str = "A single JSON object as specified by your system instructions.",
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by a CrewAI Agent/Task/Crew.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string (used as agent backstory).
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
        role: CrewAI Agent role label (descriptive only; default is generic).
        goal: CrewAI Agent goal string (descriptive only; default is generic).
        expected_output: CrewAI Task expected_output string.
    """
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415

    spec = backend_config.resolve(ws)

    from crewai import LLM, Agent, Task, Crew  # type: ignore[import]

    if spec["native"]["kind"] == "anthropic":
        llm = LLM(model=f"anthropic/{spec['native']['model']}", temperature=0)
    else:
        llm = LLM(
            model=f"ollama/{spec['native']['model']}",
            base_url=spec["base_url"].replace("/v1", ""),
            temperature=0,
            response_format={"type": "json_object"},
        )

    worker = Agent(
        role=role,
        goal=goal,
        backstory=system,
        llm=llm,
        verbose=False,
        allow_delegation=False,
    )

    def invoke(brief: str) -> str:
        task = Task(
            description=user_message_fn(brief),
            agent=worker,
            expected_output=expected_output,
        )
        crew = Crew(agents=[worker], tasks=[task], verbose=False)
        return str(crew.kickoff())

    return invoke

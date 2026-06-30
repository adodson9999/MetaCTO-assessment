"""Shared LangGraph runner — model init + single-node StateGraph.

Thin dispatchers call::

    from runners.langgraph_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw LLM output)
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Callable, Optional, Tuple


# call(prompt) -> (content_str, usage_metadata_or_None)
_CallFn = Callable[[str], Tuple[str, Optional[dict]]]


def _build_standard_call(
    ws: Path,
    max_tokens: Optional[int] = None,
) -> _CallFn:
    """Return call(prompt) -> (str, usage_meta) using ChatAnthropic or ChatOllama."""
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415

    spec = backend_config.resolve(ws)
    kind = spec["native"]["kind"]

    if kind == "openai-cli":
        # OpenAI-compatible shim (e.g. the `claude -p` CLI shim for the current
        # Claude Code session). The standard two-backend path predates this kind;
        # without this branch it falls through to ChatOllama and 404s against the
        # shim. Uses the same raw OpenAI client as _build_multicaller.
        from openai import OpenAI

        client = OpenAI(base_url=spec["base_url"], api_key="local-shim")
        model = spec["native"]["model"]

        def call(prompt: str) -> Tuple[str, Optional[dict]]:
            kwargs: dict = {
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            r = client.chat.completions.create(**kwargs)
            return r.choices[0].message.content or "", None

        return call

    if kind == "anthropic":
        from langchain_anthropic import ChatAnthropic

        kwargs: dict = {"model": spec["native"]["model"], "temperature": 0}
        if max_tokens is not None:
            kwargs["max_tokens"] = max_tokens
        llm = ChatAnthropic(**kwargs)
    else:
        from langchain_ollama import ChatOllama

        kwargs = {
            "model": spec["native"]["model"],
            "base_url": spec["base_url"].replace("/v1", ""),
            "temperature": 0,
            "format": "json",
        }
        llm = ChatOllama(**kwargs)

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        result = llm.invoke(prompt)
        content = getattr(result, "content", str(result))
        # Anthropic may return a list of content-block dicts.
        if isinstance(content, list):
            content = "".join(
                b.get("text", "") if isinstance(b, dict) else str(b)
                for b in content
            )
        usage: Optional[dict] = getattr(result, "usage_metadata", None)
        return content, usage

    return call


def _build_multicaller(ws: Path) -> _CallFn:
    """Return call(prompt) -> (str, None) supporting anthropic / openai-cli / ollama.

    Used by the four agents that carry the ``_caller()`` multi-backend pattern
    (content-type-negotiation, api-gateway-routing, soft-delete, create-postman).
    """
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415

    spec = backend_config.resolve(ws)
    kind = spec["native"]["kind"]

    if kind == "anthropic":
        from langchain_anthropic import ChatAnthropic

        llm = ChatAnthropic(model=spec["native"]["model"], temperature=0, max_tokens=1024)

        def _anthropic(p: str) -> Tuple[str, Optional[dict]]:
            result = llm.invoke(p)
            return getattr(result, "content", ""), getattr(result, "usage_metadata", None)

        return _anthropic

    if kind == "openai-cli":
        from openai import OpenAI

        client = OpenAI(base_url=spec["base_url"], api_key="local-shim")

        def _openai_call(p: str) -> Tuple[str, Optional[dict]]:
            r = client.chat.completions.create(
                model=spec["native"]["model"],
                temperature=0,
                messages=[{"role": "user", "content": p}],
            )
            return r.choices[0].message.content or "", None

        return _openai_call

    from langchain_ollama import ChatOllama

    llm = ChatOllama(
        model=spec["native"]["model"],
        base_url=spec["base_url"].replace("/v1", ""),
        temperature=0,
        format="json",
    )

    def _ollama(p: str) -> Tuple[str, Optional[dict]]:
        return getattr(llm.invoke(p), "content", ""), None

    return _ollama


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
    max_tokens: Optional[int] = None,
    multicaller: bool = False,
    on_usage: Optional[Callable[[Optional[dict]], None]] = None,
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by a compiled LangGraph StateGraph.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
        max_tokens: Optional token cap (only applied to ChatAnthropic).
        multicaller: Use the three-backend ``_caller()`` pattern instead of the
            standard two-backend model.  Set for the four agents that originally
            used ``_caller()`` (content-type, routing, soft-delete, postman).
        on_usage: Optional callback receiving ``msg.usage_metadata`` (a dict or
            ``None``) after each LLM call.  Used by the two token-tracking agents
            (queryparam, versioning) to accumulate TOTALS.
    """
    from typing import TypedDict
    from langgraph.graph import StateGraph, END  # type: ignore[import]

    call: _CallFn = (
        _build_multicaller(ws) if multicaller else _build_standard_call(ws, max_tokens)
    )

    class S(TypedDict):
        brief: str
        output: str

    def generate_node(state: S) -> S:
        prompt = f"{system}\n\n{user_message_fn(state['brief'])}"
        content, usage_meta = call(prompt)
        if on_usage is not None:
            on_usage(usage_meta)
        return {"brief": state["brief"], "output": content}

    g: StateGraph = StateGraph(S)
    g.add_node("generate", generate_node)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    graph = g.compile()

    def invoke(brief: str) -> str:
        return graph.invoke({"brief": brief, "output": ""})["output"]

    return invoke

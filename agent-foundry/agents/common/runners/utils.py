"""Shared utilities for forge-agent framework runners."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Callable, Optional


def load_system_prompt(
    subagent_md: Path,
    primary_fn: Optional[Callable[[], str]] = None,
) -> str:
    """Return the agent system prompt, honouring $FORGE_SKILL_DOC override.

    Priority order:
    1. ``$FORGE_SKILL_DOC`` env-var path (SkillOpt / EverOS evaluation gate).
    2. ``primary_fn()`` if provided — typically ``active_prompt()`` from the
       debate-gated ``*_prompt`` module.
    3. Body of *subagent_md* with the YAML front-matter block stripped.
    """
    doc = os.environ.get("FORGE_SKILL_DOC")
    if doc and Path(doc).exists():
        return Path(doc).read_text().strip()
    if primary_fn is not None:
        return primary_fn()
    text = Path(subagent_md).read_text()
    return re.sub(r"^---\n.*?\n---\n", "", text, count=1, flags=re.DOTALL).strip()


def resolve_backend(ws: Path) -> dict:
    """Call ``backend_config.resolve(ws)`` with the scripts path pre-inserted."""
    sys.path.insert(0, str(ws / "scripts"))
    import backend_config  # noqa: PLC0415
    return backend_config.resolve(ws)

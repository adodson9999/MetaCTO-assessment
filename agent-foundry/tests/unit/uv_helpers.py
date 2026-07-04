#!/usr/bin/env python3
"""Shared helpers for the unverified-bug unit suite (§7.4).

Not a test module (no ``test_`` prefix -> pytest never collects it). Every unverified
unit test imports this to locate the foundry workspace, put the common modules on
sys.path, and load the golden fixture with <<BLOB:N>> expansion.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

# agent-foundry/  (tests/unit/uv_helpers.py -> parents[2])
WS = Path(__file__).resolve().parents[2]

for sub in ("agents/common", "scripts"):
    p = str(WS / sub)
    if p not in sys.path:
        sys.path.insert(0, p)

GOLDEN_PATH = WS / "data" / "bug-reporter" / "unverified_golden.json"

_BLOB = "<<BLOB:"


def expand_blob(value: Any) -> Any:
    """Expand the ``<<BLOB:N>>`` token in a signal value to ``"x" * N`` (keeps oversized
    inputs out of the golden file). Any other value is returned unchanged."""
    if isinstance(value, str) and value.startswith(_BLOB) and value.endswith(">>"):
        n = int(value[len(_BLOB):-2])
        return "x" * n
    return value


def expand_signals(signals: dict | None) -> dict:
    """A golden ``signals`` dict with every value blob-expanded."""
    return {k: expand_blob(v) for k, v in (signals or {}).items()}


def load_golden() -> dict:
    """The parsed golden fixture."""
    return json.loads(GOLDEN_PATH.read_text())


def load_gate():
    """Import the pure forge-gate module (HF13-HF26 evaluate core)."""
    gate_dir = WS / "agents" / "general" / "bug-reporter" / "forge-gate"
    p = str(gate_dir)
    if p not in sys.path:
        sys.path.insert(0, p)
    import unverified_bug_gate as G  # noqa: E402
    return G


def load_bugreport(workspace: Path):
    """Import the materialiser and point its WORKSPACE + sandbox at a test workspace."""
    import bugreport as BR

    BR.WORKSPACE = Path(workspace).resolve()
    BR.SANDBOX_ROOT = Path(workspace).resolve()
    return BR


def materialize_unverified(BR, run_id: str, rows: list, db_available: bool,
                           workspace: Path) -> tuple[list, list]:
    """Materialise a list of missing-docs mismatch rows into unverified bugs + the index.
    Returns (ledger_rows, index_entries). Ledger rows carry the routing outcome fields the
    gate expects (outcome, unverified_bug_id, category, exclude_from_cicd)."""
    counters: dict = {}
    entries: list = []
    out_rows: list = []
    for r in rows:
        report = BR.write_unverified_bug(run_id, dict(r), counters, db_available, workspace=workspace)
        row = dict(r)
        row.update({
            "outcome": "missing-docs",
            "reviewer_verdict": "missing-docs",
            "exclude_from_cicd": True,
            "unverified_bug_id": report["bug_id"],
            "category": report["category"],
        })
        out_rows.append(row)
        entries.append(report["_meta"]["index_entry"])
    BR.write_unverified_index(run_id, entries, workspace=workspace)
    return out_rows, entries

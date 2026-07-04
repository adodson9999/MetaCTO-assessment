#!/usr/bin/env python3
"""Shared fixtures for the unverified-bug unit suite (§7.4).

Provides a deterministic materialised run in a tmp workspace: FORGE_BUG_DATE/FORGE_BUG_TIME
pin the folder date/time so every path + report is reproducible, and the materialiser writes
into tmp_path (its sandbox + WORKSPACE are redirected there).
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))  # tests/unit on sys.path
import uv_helpers as H  # noqa: E402

RUN_ID = "RUN-20260701-120000"


@pytest.fixture
def run_id() -> str:
    return RUN_ID


@pytest.fixture
def deterministic_time(monkeypatch) -> None:
    monkeypatch.setenv("FORGE_BUG_DATE", "2026-07-01")
    monkeypatch.setenv("FORGE_BUG_TIME", "12-00-00")


@pytest.fixture
def bugreport(deterministic_time, tmp_path):
    """(BR module, workspace Path) with the materialiser aimed at a fresh tmp workspace."""
    return H.load_bugreport(tmp_path), tmp_path

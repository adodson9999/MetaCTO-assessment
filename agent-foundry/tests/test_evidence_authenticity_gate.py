#!/usr/bin/env python3
"""G24 evidence-authenticity gate: proves the gate rejects placeholder evidence (a text 'replay'
screenshot, a static cast, an agent-stdout log) and passes only real captured evidence (a PNG
screenshot, a stepped .cast, a server-origin log). Server log is best-effort: a bug with no log
still passes.

Run:  agent-foundry/.venv/bin/python -m pytest agent-foundry/tests/test_evidence_authenticity_gate.py
"""
from __future__ import annotations

import json
import os
import shutil
import struct
import subprocess
import sys
import zlib
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
sys.path.insert(0, str(WS / "scripts"))
import guardrails as G  # noqa: E402


def _png(path: Path) -> None:
    """Minimal valid 1x1 PNG (magic + IHDR + IDAT + IEND)."""
    def chunk(typ, data):
        return (struct.pack(">I", len(data)) + typ + data
                + struct.pack(">I", zlib.crc32(typ + data) & 0xFFFFFFFF))
    path.parent.mkdir(parents=True, exist_ok=True)
    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    idat = zlib.compress(b"\x00\x00\x00\x00")
    path.write_bytes(b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
                     + chunk(b"IDAT", idat) + chunk(b"IEND", b""))


def _mp4(path: Path) -> None:
    """A real multi-frame H.264 MP4 via ffmpeg (skips if ffmpeg absent)."""
    if not shutil.which("ffmpeg"):
        import pytest
        pytest.skip("ffmpeg not available")
    path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi",
                    "-i", "color=c=black:s=64x64:d=1:r=6", "-c:v", "libx264",
                    "-pix_fmt", "yuv420p", str(path)], check=True, timeout=60)


def _cast(path: Path, stepped: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    header = {"version": 2, "width": 80, "height": 24, "timestamp": 1}
    if stepped:
        events = [[0.1, "o", "$ curl -i http://localhost:8890/auth/me\r\n"],
                  [0.3, "o", "HTTP/1.1 500\r\n"], [0.4, "o", "{\r\n"],
                  [0.5, "o", '  "error": "x"\r\n'], [0.6, "o", "}\r\n"], [0.7, "o", "$ \r\n"]]
    else:
        events = [[0.1, "o", "static frame, no steps\r\n"]]
    path.write_text("\n".join([json.dumps(header)] + [json.dumps(e) for e in events]) + "\n")


def _bug(tree: Path, agent: str, bug_id: str, shot: str, cast: str, log: str | None) -> None:
    d = tree / agent / "verified_bugs"
    d.mkdir(parents=True, exist_ok=True)
    atts = {"screenshot": shot, "recording": cast}
    if log:
        atts["log"] = log
    (d / f"{bug_id}.json").write_text(json.dumps({"id": bug_id, "attachments": atts}))


def test_g24_passes_real_evidence(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    _png(out / "BugReport/a/screenshots/BUG-1.png")
    _mp4(out / "BugReport/a/recordings/BUG-1.mp4")
    (out / "BugReport/a/logs/BUG-1.log").parent.mkdir(parents=True, exist_ok=True)
    (out / "BugReport/a/logs/BUG-1.log").write_text(
        "HTTP Request - GET:500:{\"response_time_ms\":\"1.2\"}\n")
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1.png",
         "BugReport/a/recordings/BUG-1.mp4", "BugReport/a/logs/BUG-1.log")
    r = G.g24_evidence_authenticity(out)
    assert r["status"] == "PASS", r["detail"]


def test_g24_allows_missing_log(tmp_path):
    """Server log is best-effort: a bug with a PNG + stepped cast but NO log still passes."""
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    _png(out / "BugReport/a/screenshots/BUG-1.png")
    _mp4(out / "BugReport/a/recordings/BUG-1.mp4")
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1.png",
         "BugReport/a/recordings/BUG-1.mp4", None)
    assert G.g24_evidence_authenticity(out)["status"] == "PASS"


def test_g24_rejects_text_replay_screenshot(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    (out / "BugReport/a/screenshots").mkdir(parents=True)
    (out / "BugReport/a/screenshots/BUG-1-replay.txt").write_text("=== REPLAY ===")
    _mp4(out / "BugReport/a/recordings/BUG-1.mp4")
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1-replay.txt",
         "BugReport/a/recordings/BUG-1.mp4", None)
    r = G.g24_evidence_authenticity(out)
    assert r["status"] == "FAIL" and "replay.txt" in r["detail"]


def test_g24_rejects_static_image_recording(tmp_path):
    """A still image passed off as the recording (not a real video) fails."""
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    _png(out / "BugReport/a/screenshots/BUG-1.png")
    _png(out / "BugReport/a/recordings/BUG-1.gif")  # a non-animated image, not a real video
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1.png",
         "BugReport/a/recordings/BUG-1.gif", None)
    r = G.g24_evidence_authenticity(out)
    assert r["status"] == "FAIL" and "video recording" in r["detail"]

def test_g24_rejects_static_cast(tmp_path):
    """A .cast fallback that is a single static frame (no steps) still fails."""
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    _png(out / "BugReport/a/screenshots/BUG-1.png")
    _cast(out / "BugReport/a/recordings/BUG-1.cast", stepped=False)
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1.png",
         "BugReport/a/recordings/BUG-1.cast", None)
    r = G.g24_evidence_authenticity(out)
    assert r["status"] == "FAIL" and "video recording" in r["detail"]


def test_g24_rejects_non_server_log(tmp_path):
    out = tmp_path / "2026-07-04" / "00-00-00"
    tree = out / "BugReport"
    _png(out / "BugReport/a/screenshots/BUG-1.png")
    _mp4(out / "BugReport/a/recordings/BUG-1.mp4")
    (out / "BugReport/a/logs/BUG-1.log").parent.mkdir(parents=True, exist_ok=True)
    (out / "BugReport/a/logs/BUG-1.log").write_text("agent stdout: ran 5 cases\n")
    _bug(tree, "a", "BUG-1", "BugReport/a/screenshots/BUG-1.png",
         "BugReport/a/recordings/BUG-1.mp4", "BugReport/a/logs/BUG-1.log")
    r = G.g24_evidence_authenticity(out)
    assert r["status"] == "FAIL" and "server-origin" in r["detail"]

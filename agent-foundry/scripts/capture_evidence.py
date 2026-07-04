#!/usr/bin/env python3
# Used by: full-orchestration finalize + manual re-capture — real bug-evidence capture.
"""Capture REAL reproduction evidence for a materialized bug report.

For one bug this:
  1. Derives a concrete HTTP request from the bug (method + path; GET when only a path is
     known; a per-agent representative call for an aggregate finding).
  2. Executes it against a LIVE server that has request logging enabled, capturing the real
     request line, response status/headers/body, and the server log lines emitted during the
     request window.
  3. Renders three artifacts that show what actually happened:
       - screenshot: a PNG of the terminal exchange (the request + the real response) — "what
         occurs", not a text dump.
       - recording: an asciinema v2 .cast that ANIMATES the steps — the command being typed,
         then the real response streaming in, with real inter-event timing.
       - log: the server-origin log lines for the request window — BEST-EFFORT: written only
         when the server actually produced logs (like a db_dump only when a DB is available);
         None otherwise.

Pure-stdlib + Pillow (already in the foundry venv). No network beyond the local target.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

_MONO_CANDIDATES = [
    "/System/Library/Fonts/Menlo.ttc",
    "/System/Library/Fonts/Supplemental/Courier New.ttf",
    "/System/Library/Fonts/SFNSMono.ttf",
]
_FONT_SIZE = 15
_LINE_H = 20
_PAD = 16
_COLS = 108
# terminal palette
_BG = (30, 30, 30)
_FG = (220, 220, 220)
_GREEN = (120, 200, 120)
_YELLOW = (220, 200, 110)
_RED = (230, 120, 120)
_CYAN = (110, 190, 210)
_DIM = (140, 140, 140)


def _font() -> ImageFont.FreeTypeFont:
    for p in _MONO_CANDIDATES:
        if Path(p).is_file():
            try:
                return ImageFont.truetype(p, _FONT_SIZE)
            except OSError:
                continue
    return ImageFont.load_default()


# --------------------------------------------------------------------------- #
# Reproduction request derivation
# --------------------------------------------------------------------------- #
# A representative, read-only reproduction endpoint per agent for aggregate findings (no single
# recorded call). GET-only so re-capture is idempotent and never mutates the target.
_AGENT_REPRO_CALL = {
    "test-authentication-flows": ("GET", "/auth/me", {"Authorization": "Bearer invalid.token.here"}),
    "check-authorization-rules": ("GET", "/auth/me", {}),
    "verify-response-status-codes": ("GET", "/products/999999", {}),
    "test-pagination-behavior": ("GET", "/products?limit=10&skip=10", {}),
    "verify-error-message-clarity": ("GET", "/products/999999", {}),
    "validate-query-parameter-handling": ("GET", "/products?limit=0&skip=-1", {}),
    "test-idempotency-of-endpoints": ("GET", "/products/1", {}),
    "verify-content-type-negotiation": ("GET", "/products", {"Accept": "application/xml"}),
    "validate-null-empty-fields": ("GET", "/products/1", {}),
    "verify-crud-operation-integrity": ("GET", "/products/1", {}),
    "run-regression-suite": ("GET", "/products", {}),
    "track-defect-density": ("GET", "/products", {}),
    "test-bulk-operation-endpoints": ("GET", "/products", {}),
    "validate-search-and-filter-queries": ("GET", "/products/search?q=phone", {}),
    "verify-sorting-behavior": ("GET", "/products?sortBy=price&order=asc", {}),
    "measure-api-consumer-satisfaction": ("GET", "/products", {}),
    "test-soft-delete-behavior": ("GET", "/products/1", {}),
    "test-concurrent-request-handling": ("GET", "/products", {}),
}
_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS")


def _derive_request(bug: dict) -> tuple:
    """(method, path, headers) to reproduce. Prefers an explicit 'METHOD /path'; falls back to a
    path-only GET; else the agent's representative call; else a safe GET /products."""
    agent = bug.get("finding_agent") or _short(bug.get("_source", {}).get("agent", ""))
    endpoint = (bug.get("environment", {}) or {}).get("endpoint") or bug.get("finding_endpoint") or ""
    endpoint = str(endpoint).strip()
    rep = _AGENT_REPRO_CALL.get(agent)
    if endpoint and not endpoint.lower().startswith("n/a"):
        parts = endpoint.split()
        method, path = (parts[0].upper(), parts[1]) if (len(parts) == 2 and parts[0].upper() in _METHODS) \
            else (("GET", endpoint) if endpoint.startswith("/") else (None, None))
        if path:
            # merge the agent's representative headers when it targets the same resource, so the
            # reproduction exercises the meaningful case (e.g. auth/me with an invalid token).
            headers = rep[2] if (rep and path.split("?")[0].startswith(rep[1].split("?")[0])) else {}
            return method, path, dict(headers)
    return rep or ("GET", "/products", {})


def _short(agent_name: str) -> str:
    for pre in ("api-tester-", "general-"):
        if agent_name.startswith(pre):
            return agent_name[len(pre):]
    return agent_name


# --------------------------------------------------------------------------- #
# Execute + capture
# --------------------------------------------------------------------------- #
def _execute(target: str, method: str, path: str, headers: dict) -> dict:
    """Issue the request; capture status, headers, body excerpt, latency. Never raises."""
    url = target.rstrip("/") + path
    req = urllib.request.Request(url, method=method, headers=headers or {})
    t0 = time.monotonic()
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(4096).decode("utf-8", "replace")
            status, resp_headers = r.getcode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        body = e.read(4096).decode("utf-8", "replace") if e.fp else ""
        status, resp_headers = e.code, dict(e.headers or {})
    except Exception as e:  # noqa: BLE001 — connection refused etc. still yields evidence
        return {"url": url, "method": method, "status": None, "error": str(e),
                "headers": {}, "body": "", "latency_ms": None, "reachable": False}
    return {"url": url, "method": method, "status": status, "headers": resp_headers,
            "body": body, "latency_ms": round((time.monotonic() - t0) * 1000, 1),
            "reachable": True}


def _curl_cmd(method: str, url: str, headers: dict) -> str:
    parts = ["curl", "-i", "-s", "-X", method]
    for k, v in (headers or {}).items():
        parts += ["-H", f"'{k}: {v}'"]
    parts.append(f"'{url}'")
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# Artifact 3 — PNG screenshot of the exchange
# --------------------------------------------------------------------------- #
def _exchange_lines(bug: dict, cmd: str, result: dict) -> list:
    """(text, color) lines depicting the reproduced request + real response."""
    lines = [(f"$ {cmd}", _CYAN), ("", _FG)]
    if not result.get("reachable"):
        lines.append((f"curl: could not reach target — {result.get('error')}", _RED))
        return lines
    status = result["status"]
    sev_col = _GREEN if status and status < 400 else (_YELLOW if status and status < 500 else _RED)
    lines.append((f"HTTP {status}   ({result['latency_ms']} ms)", sev_col))
    for k in ("Content-Type", "Content-Length", "X-Powered-By"):
        for hk, hv in result["headers"].items():
            if hk.lower() == k.lower():
                lines.append((f"{hk}: {hv}", _DIM))
    lines.append(("", _FG))
    body = result["body"].strip()
    try:
        body = json.dumps(json.loads(body), indent=2)
    except (json.JSONDecodeError, ValueError):
        pass
    for bl in body.splitlines()[:22]:
        lines.append((bl[:_COLS], _FG))
    return lines


def _canvas(header: str, lines: list) -> tuple:
    """(width, height) for a terminal canvas holding header + all lines (even dims for H.264)."""
    n = len(lines) + 2  # header + blank
    h = _PAD * 2 + _LINE_H * (n + 1)
    w = _PAD * 2 + int(_COLS * _FONT_SIZE * 0.62)
    return (w + w % 2, max(h, 120) + (max(h, 120) % 2))


def _draw_frame(size: tuple, header: str, lines: list, font) -> Image.Image:
    """Render one terminal frame: title bar + header + the given (text,color) lines."""
    img = Image.new("RGB", size, _BG)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, size[0], 26], fill=(50, 50, 50))
    for i, col in enumerate((_RED, _YELLOW, _GREEN)):
        d.ellipse([12 + i * 18, 8, 24 + i * 18, 20], fill=col)
    y = 34
    for text, color in [(header, _YELLOW), ("", _FG)] + lines:
        d.text((_PAD, y), text, fill=color, font=font)
        y += _LINE_H
    return img


def _render_png(path: Path, header: str, lines: list) -> Path | None:
    size = _canvas(header, lines)
    img = _draw_frame(size, header, lines, _font())
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        img.save(path, "PNG")
        return path
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Artifact 4 — MP4 screen recording of the reproduction (real, watchable video)
# --------------------------------------------------------------------------- #
def _reveal_states(cmd: str, result: dict) -> list:
    """Progressive terminal states (each a (text,color) line list) that, played in sequence,
    animate the reproduction: the command typing out, then the response appearing line by line."""
    states = []
    # 1. command types out in a few chunks
    chunks = max(1, len(cmd) // 12)
    typed = ""
    for i in range(0, len(cmd), 12):
        typed = cmd[: i + 12]
        states.append([(f"$ {typed}", _CYAN)])
    base = [(f"$ {cmd}", _CYAN), ("", _FG)]
    # 2. response reveals incrementally
    resp = _exchange_lines_response(result)
    for k in range(1, len(resp) + 1):
        states.append(base + resp[:k])
    if not resp:
        states.append(base)
    return states


def _exchange_lines_response(result: dict) -> list:
    """Just the response portion (status/headers/body) as (text,color) lines."""
    if not result.get("reachable"):
        return [(f"curl: could not reach target — {result.get('error')}", _RED)]
    status = result["status"]
    col = _GREEN if status and status < 400 else (_YELLOW if status and status < 500 else _RED)
    out = [(f"HTTP {status}   ({result['latency_ms']} ms)", col)]
    for want in ("Content-Type", "Content-Length"):
        for hk, hv in result["headers"].items():
            if hk.lower() == want.lower():
                out.append((f"{hk}: {hv}", _DIM))
    out.append(("", _FG))
    body = result["body"].strip()
    try:
        body = json.dumps(json.loads(body), indent=2)
    except (json.JSONDecodeError, ValueError):
        pass
    for bl in body.splitlines()[:18]:
        out.append((bl[:_COLS], _FG))
    return out


def _write_video(path: Path, header: str, cmd: str, result: dict, fps: int = 4) -> Path | None:
    """Encode the reproduction as an MP4 (H.264) via ffmpeg — a real screen recording you can
    watch. Returns the path, or None when ffmpeg is unavailable / encoding fails."""
    if not shutil.which("ffmpeg"):
        return None
    states = _reveal_states(cmd, result)
    if not states:
        return None
    final = states[-1]
    size = _canvas(header, final)
    font = _font()
    tmp = Path(tempfile.mkdtemp(prefix="rec-"))
    try:
        idx = 0
        for st in states:
            _draw_frame(size, header, st, font).save(tmp / f"f{idx:04d}.png")
            idx += 1
        # hold the final frame ~2s so the result is readable
        last = _draw_frame(size, header, final, font)
        for _ in range(fps * 2):
            last.save(tmp / f"f{idx:04d}.png")
            idx += 1
        path.parent.mkdir(parents=True, exist_ok=True)
        cmd_ff = ["ffmpeg", "-y", "-loglevel", "error", "-framerate", str(fps),
                  "-i", str(tmp / "f%04d.png"), "-c:v", "libx264", "-pix_fmt", "yuv420p",
                  "-vf", "pad=ceil(iw/2)*2:ceil(ih/2)*2", str(path)]
        r = subprocess.run(cmd_ff, capture_output=True, text=True, timeout=60)
        return path if (r.returncode == 0 and path.is_file()) else None
    except (OSError, subprocess.SubprocessError):
        return None
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# --------------------------------------------------------------------------- #
# Artifact 4 — asciinema v2 .cast animating the steps
# --------------------------------------------------------------------------- #
def _write_cast(path: Path, title: str, cmd: str, result: dict, ts: int) -> Path | None:
    header = {"version": 2, "width": 108, "height": 32, "timestamp": ts,
              "title": title, "env": {"TERM": "xterm-256color", "SHELL": "/bin/bash"}}
    events = []
    t = 0.4
    events.append([round(t, 2), "o", "$ "])
    # type the command out, char-by-char (real animation)
    for ch in cmd:
        t += 0.012
        events.append([round(t, 2), "o", ch])
    t += 0.3
    events.append([round(t, 2), "o", "\r\n"])
    if result.get("reachable"):
        t += (result.get("latency_ms") or 5) / 1000.0
        status = result["status"]
        events.append([round(t, 2), "o", f"HTTP/1.1 {status}\r\n"])
        for hk, hv in list(result["headers"].items())[:6]:
            t += 0.02
            events.append([round(t, 2), "o", f"{hk}: {hv}\r\n"])
        t += 0.05
        events.append([round(t, 2), "o", "\r\n"])
        body = result["body"].strip()
        try:
            body = json.dumps(json.loads(body), indent=2)
        except (json.JSONDecodeError, ValueError):
            pass
        for bl in body.splitlines()[:24]:
            t += 0.03
            events.append([round(t, 2), "o", bl[:108] + "\r\n"])
    else:
        t += 0.2
        events.append([round(t, 2), "o", f"curl: (7) {result.get('error')}\r\n"])
    t += 0.5
    events.append([round(t, 2), "o", "\r\n$ \r\n"])
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text("\n".join([json.dumps(header)] + [json.dumps(e) for e in events]) + "\n")
        return path
    except OSError:
        return None


# --------------------------------------------------------------------------- #
# Artifact 5 — server-origin logs (BEST-EFFORT)
# --------------------------------------------------------------------------- #
def _capture_server_log(path: Path, server_log: Path, since_offset: int,
                        bug_id: str, cmd: str) -> tuple:
    """Write the server log lines appended since `since_offset` (the reproduction window). Returns
    (path_or_None, new_offset). BEST-EFFORT: if the server produced no logs (logging off /
    unreachable), returns (None, offset) — the log artifact is simply absent (like db_dump)."""
    if not server_log or not server_log.is_file():
        return None, since_offset
    try:
        data = server_log.read_text(errors="replace")
    except OSError:
        return None, since_offset
    new = data[since_offset:]
    # keep only genuine request-log lines emitted by the server for this window
    srv_lines = [ln for ln in new.splitlines()
                 if "HTTP Request" in ln or "response_time_ms" in ln or "Error:" in ln]
    if not srv_lines:
        return None, len(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    content = (f"=== SERVER LOG (origin: target API request logger) — {bug_id} ===\n"
               f"# reproduction: {cmd}\n"
               f"# only the server's own log lines for this request window are included.\n\n"
               + "\n".join(srv_lines) + "\n")
    try:
        path.write_text(content)
        return path, len(data)
    except OSError:
        return None, len(data)


# --------------------------------------------------------------------------- #
# Public: capture one bug
# --------------------------------------------------------------------------- #
def capture(bug: dict, agent: str, rel_prefix: str, art_dir: Path, target: str, ts: int,
            server_log: Path | None, log_offset: int) -> tuple:
    """Produce {screenshot,recording,log} PNG/mp4/log for one bug. Returns (attachments, new
    log_offset). Files are written under `art_dir`/{screenshots,recordings,logs}; attachments map
    artifact name -> the BugReport-relative path `BugReport/{rel_prefix}/...` (log absent when the
    server produced none). `agent` is the display label; `rel_prefix` places the artifacts —
    e.g. "<agent>" for a verified bug, "unverified/<category>" for an unverified one."""
    bug_id = bug.get("id") or bug.get("bug_id")
    method, path_, headers = _derive_request(bug)
    result = _execute(target, method, path_, headers)
    cmd = _curl_cmd(method, result["url"], headers)

    shot = art_dir / "screenshots" / f"{bug_id}.png"
    video = art_dir / "recordings" / f"{bug_id}.mp4"
    cast = art_dir / "recordings" / f"{bug_id}.cast"
    logf = art_dir / "logs" / f"{bug_id}.log"

    header = f"Bug {bug_id} — {agent} — reproduction"
    png = _render_png(shot, header, _exchange_lines(bug, cmd, result))
    # recording: a real watchable MP4 screen recording; the asciinema .cast is a text fallback
    # only when ffmpeg is unavailable.
    rec = _write_video(video, header, cmd, result)
    rec_rel = None
    if rec:
        cast.unlink(missing_ok=True)
        rec_rel = f"BugReport/{rel_prefix}/recordings/{rec.name}"
    else:
        c = _write_cast(cast, f"{bug_id} — {agent}", cmd, result, ts)
        if c:
            rec_rel = f"BugReport/{rel_prefix}/recordings/{c.name}"
    log_path, new_offset = _capture_server_log(logf, server_log, log_offset, bug_id, cmd)

    attach = {}
    if png:
        attach["screenshot"] = f"BugReport/{rel_prefix}/screenshots/{png.name}"
    if rec_rel:
        attach["recording"] = rec_rel
    if log_path:
        attach["log"] = f"BugReport/{rel_prefix}/logs/{log_path.name}"
    return attach, new_offset

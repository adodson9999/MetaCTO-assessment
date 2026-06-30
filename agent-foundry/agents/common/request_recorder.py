# Used by: shared — captures EVERY distinct HTTP request an api-tester agent sends, so the Postman
# collection can include all of them (guardrail G19). Activated per-executor via sitecustomize when
# FORGE_RECORD_REQUESTS=1; writes results/runs/<RID>/requests/<agent>.json. No harness edits needed.
"""Wrap urllib.request.urlopen to record each agent's outbound API calls, de-duplicated by
(method, path, query, body). One process per agent => one JSON file per agent. The EverOS memory
telemetry endpoint is excluded (it is not a test request)."""
from __future__ import annotations

import atexit
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit

_LOCK = threading.Lock()
_SEEN: dict[tuple, dict] = {}            # dedupe key -> request record
_INSTALLED = False


def _agent() -> str:
    return os.environ.get("FORGE_AGENT", "unknown-agent")


def _out_path() -> Path | None:
    ws = os.environ.get("FORGE_WORKSPACE")
    rid = os.environ.get("FORGE_RUN_ID")
    if not ws or not rid:
        return None
    return Path(ws) / "results" / "runs" / rid / "requests" / f"{_agent()}.json"


# Paths/ports that are NOT the API-under-test: the agent's own LLM backend (OpenAI-compatible shim
# + ollama) and the EverOS memory telemetry. Excluded from the collection.
_EXCLUDE_PATH_MARKERS = ("/v1/chat/completions", "/v1/completions", "/v1/models", "/v1/embeddings",
                         "/api/chat", "/api/generate", "/api/tags", "/api/embeddings",
                         "/api/v1/memory/")
_EXCLUDE_PORTS = (":8787", ":11434", ":8000")   # claude-cli shim, ollama, everos


def path_excluded(path: str) -> bool:
    p = (path or "").lower()
    return any(m in p for m in _EXCLUDE_PATH_MARKERS)


def _excluded(url: str) -> bool:
    low = (url or "").lower()
    return path_excluded(low) or any(port in low for port in _EXCLUDE_PORTS)


def _record(method: str, url: str, body, status) -> None:
    if _excluded(url):
        return
    parts = urlsplit(url)
    path = parts.path or "/"
    query = dict(p.split("=", 1) for p in parts.query.split("&") if "=" in p) if parts.query else {}
    bval = None
    if body is not None:
        raw = body.decode("utf-8", "replace") if isinstance(body, (bytes, bytearray)) else str(body)
        try:
            bval = json.loads(raw)
        except (ValueError, json.JSONDecodeError):
            bval = raw
    key = (method, path, parts.query, json.dumps(bval, sort_keys=True) if bval is not None else "")
    with _LOCK:
        rec = _SEEN.get(key)
        if rec is None:
            _SEEN[key] = {"method": method, "path": path, "query": query, "body": bval,
                          "status": status, "count": 1}
        else:
            rec["count"] += 1
            if rec.get("status") is None:
                rec["status"] = status


def _flush() -> None:
    out = _out_path()
    if out is None or not _SEEN:
        return
    out.parent.mkdir(parents=True, exist_ok=True)
    with _LOCK:
        records = list(_SEEN.values())
    try:
        out.write_text(json.dumps({"agent": _agent(), "requests": records}, indent=2))
    except OSError:
        pass


def install() -> None:
    """Idempotently wrap urllib.request.urlopen + register the atexit flush."""
    global _INSTALLED
    if _INSTALLED or not os.environ.get("FORGE_RECORD_REQUESTS"):
        return
    _INSTALLED = True
    _orig = urllib.request.urlopen

    def _patched(url, *args, **kwargs):
        if isinstance(url, urllib.request.Request):
            method = url.get_method()
            full = url.full_url
            body = url.data
        else:
            method, full, body = "GET", str(url), kwargs.get("data")
        try:
            resp = _orig(url, *args, **kwargs)
            try:
                code = getattr(resp, "status", None) or resp.getcode()
            except Exception:  # noqa: BLE001
                code = None
            _record(method, full, body, code)
            return resp
        except urllib.error.HTTPError as e:
            _record(method, full, body, e.code)
            raise
        except Exception:  # noqa: BLE001
            _record(method, full, body, None)
            raise

    urllib.request.urlopen = _patched
    atexit.register(_flush)

#!/usr/bin/env python3
"""Minimal OpenAI-compatible shim over the `claude` CLI (claude.ai subscription).

Why this exists: for the content-type-negotiation build the user asked for the
CLAUDE backend, but the ANTHROPIC_API_KEY in this environment is out of credits.
The `claude` CLI still works via the claude.ai subscription when ANTHROPIC_API_KEY
is UNSET. This shim exposes that subscription path behind the OpenAI
/v1/chat/completions protocol so all four framework agents (which already speak
OpenAI-compatible HTTP) can use one uniform, working Claude backend without API
credits. It is NOT Ollama and NOT a cloud relay — every completion is a local
`claude -p` subprocess.

Endpoints:
    GET  /v1/models                    -> a single fake model entry (client init)
    POST /v1/chat/completions          -> run claude -p, return OpenAI shape
    POST /chat/completions             -> same (some clients omit /v1)

stdlib only. Bind loopback. One claude subprocess per request.

Usage:
    python scripts/claude_cli_shim.py --port 8787 [--model claude-haiku-4-5]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODEL = os.environ.get("FORGE_SHIM_MODEL", "claude-haiku-4-5")
CLAUDE_TIMEOUT = int(os.environ.get("FORGE_SHIM_TIMEOUT", "120"))


def _claude(prompt: str, model: str) -> str:
    """One-shot claude CLI call on the subscription (ANTHROPIC_API_KEY unset)."""
    env = dict(os.environ)
    env.pop("ANTHROPIC_API_KEY", None)   # force the claude.ai subscription path
    try:
        proc = subprocess.run(
            ["claude", "-p", prompt, "--output-format", "text", "--model", model],
            stdin=subprocess.DEVNULL, capture_output=True, text=True,
            env=env, timeout=CLAUDE_TIMEOUT)
        if proc.returncode == 0:
            return proc.stdout.strip()
        return proc.stdout.strip() or proc.stderr.strip()
    except Exception as e:  # noqa
        return f'{{"_shim_error": {json.dumps(str(e))}}}'


def _prompt_from_messages(messages: list[dict]) -> str:
    sys_parts, turns = [], []
    for m in messages:
        role = m.get("role", "user")
        content = m.get("content", "")
        if isinstance(content, list):  # OpenAI content blocks
            content = "".join(b.get("text", "") for b in content if isinstance(b, dict))
        if role == "system":
            sys_parts.append(content)
        else:
            turns.append(content)
    parts = []
    if sys_parts:
        parts.append("\n".join(sys_parts))
    parts.extend(turns)
    return "\n\n".join(p for p in parts if p)


class Handler(BaseHTTPRequestHandler):
    server_version = "claude-cli-shim/1.0"

    def log_message(self, *a):  # quiet
        pass

    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": [
                {"id": MODEL, "object": "model", "owned_by": "anthropic-subscription"}]})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self):
        if not self.path.endswith("/chat/completions"):
            self._json(404, {"error": "not found"})
            return
        length = int(self.headers.get("Content-Length", "0") or 0)
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except Exception:  # noqa
            req = {}
        model = req.get("model", MODEL)
        if "/" in model:           # strip "openai/" or "anthropic/" prefixes from clients
            model = model.split("/", 1)[1]
        if not model.startswith("claude"):
            model = MODEL
        prompt = _prompt_from_messages(req.get("messages", []))
        text = _claude(prompt, model)
        self._json(200, {
            "id": f"chatcmpl-shim-{int(time.time()*1000)}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0},
        })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--model", default=MODEL)
    a = ap.parse_args()
    globals()["MODEL"] = a.model
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"claude-cli-shim on http://{a.host}:{a.port}/v1 (model {a.model}) — "
          f"each completion = one `claude -p` on the subscription", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())

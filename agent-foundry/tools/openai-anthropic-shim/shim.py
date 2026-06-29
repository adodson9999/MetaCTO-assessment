#!/usr/bin/env python3
"""Dependency-light OpenAI -> Anthropic shim (stdlib + the anthropic SDK only).

The documented OpenAI-compatible path for the claude_sdk + subagent agents is a local
LiteLLM proxy. When `litellm[proxy]` (fastapi/uvicorn) is not installed, this tiny
stdlib server provides the same contract — POST /chat/completions and the
/health/liveliness probe — by translating to the Anthropic Messages API via the
already-present `anthropic` SDK. Same wire shape the agents already speak, so nothing
in the agents changes.

Binds 127.0.0.1 only. The single outbound call is to the Anthropic API (the explicit,
opt-in cloud backend for this task — skill invariant 5). Reads ANTHROPIC_API_KEY from
the environment; never logs it.

Usage:
    python shim.py --host 127.0.0.1 --port 4000
"""
from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


def _to_anthropic(messages: list[dict]) -> tuple[str, list[dict]]:
    """Split OpenAI-style messages into (system_text, anthropic_messages)."""
    system_parts, conv = [], []
    for m in messages:
        role = m.get("role")
        content = m.get("content", "")
        if role == "system":
            system_parts.append(content)
            continue
        conv.append({"role": "assistant" if role == "assistant" else "user",
                     "content": content})
    if not conv:
        conv = [{"role": "user", "content": ""}]
    return "\n\n".join(system_parts), conv


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # noqa
        return

    def _send(self, code: int, body: dict) -> None:
        payload = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Connection", "close")
        self.close_connection = True
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:
        if self.path.startswith("/health"):
            self._send(200, {"status": "healthy"})
            return
        self._send(404, {"error": "not found"})

    def do_POST(self) -> None:
        if not self.path.endswith("/chat/completions"):
            self._send(404, {"error": "not found"})
            return
        n = int(self.headers.get("Content-Length", 0) or 0)
        try:
            req = json.loads(self.rfile.read(n) or b"{}")
        except Exception:  # noqa
            self._send(400, {"error": "invalid json"})
            return

        model = req.get("model", "claude-haiku-4-5")
        temperature = req.get("temperature", 0)
        system, conv = _to_anthropic(req.get("messages", []))
        # Nudge JSON-only output when the caller requested a json response_format.
        if (req.get("response_format") or {}).get("type") == "json_object":
            system = (system + "\n\nRespond with only a single JSON object and nothing else.").strip()

        try:
            import anthropic
            client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
            msg = client.messages.create(
                model=model, max_tokens=2048, temperature=temperature,
                system=system or anthropic.NOT_GIVEN, messages=conv)
            text = "".join(getattr(b, "text", "") for b in msg.content)
        except Exception as e:  # noqa
            self._send(502, {"error": {"message": f"{type(e).__name__}: {e}"}})
            return

        self._send(200, {
            "id": "chatcmpl-shim", "object": "chat.completion", "model": model,
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": text}}],
        })


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=4000)
    a = ap.parse_args()
    srv = ThreadingHTTPServer((a.host, a.port), Handler)
    print(f"openai-anthropic-shim listening on http://{a.host}:{a.port} "
          f"(POST /chat/completions -> Anthropic Messages API)", flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

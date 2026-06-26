"""Shared, deterministic plumbing for the four multipart/form-data handling agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the upload-endpoint catalogue from
    data/test-multipart-form-data-handling/multipart_spec.json
  - build the compact per-endpoint multipart-contract brief handed to the agent
  - execute whatever plan the agent emitted, building the EXACT bodies in memory:
      * VALID CREATE: multipart POST with the two text parts + a 50 KB PNG file part;
        record status, whether each text field came back EXACTLY, whether the body
        carries a document_url, and the returned id
      * MD5 ROUND-TRIP: if a document_url is present, GET it and byte-for-byte MD5
        compare to the uploaded PNG; otherwise record 'no_url'
      * PERSISTED READBACK: GET readback_path with the returned id; persisted iff both
        text fields come back
      * OVERSIZED: multipart POST with a file of max_allowed_file_bytes+1 bytes; record status
      * MISSING FIELD: multipart POST omitting the first text part; record status + whether
        the error message references the omitted field name
      * WRONG CONTENT-TYPE: POST the same two fields as an application/json body; record status
    (host + method guards: localhost only, GET/POST only, file size capped)
  - evaluate every scenario (shared multipart_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified. Its /add routes are non-persistent
simulations (these POSTs change no server state) and it deletes any parsed multipart
file; we never edit DummyJSON's code or data.

The framework-specific part — turning one endpoint's brief into the multipart test plan
via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "test-multipart-form-data-handling" / "multipart_spec.json"

# Safety cap so a malformed plan can never make the harness allocate a huge file or push
# a huge body at the target. Legitimate plans top out at max_allowed_file_bytes + 1.
MAX_FILE_BYTES = 32 * 1024 * 1024  # 32 MiB
_BOUNDARY = "forgeMultipartFormDataBoundary7MA4YWxkTrZu0gW"

# Keys a conforming create response might carry the stored-file URL under.
_DOC_URL_KEYS = ("document_url", "documentUrl", "document", "url", "file_url", "fileUrl")

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import multipart_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Sandbox + host + method guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


def _assert_method(method: str) -> None:
    if method not in ("GET", "POST", "PUT"):
        raise PermissionError(f"refusing method {method}: only GET/POST/PUT allowed")


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = list(spec["endpoints"])
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["endpoint"] in wanted or c.get("slug") in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous multipart contract handed to the LLM."""
    a, b = cfg["text_field_a"], cfg["text_field_b"]
    return "\n".join([
        f"endpoint_path: {cfg['endpoint']}",
        f"method: {cfg['method']}",
        f"expected_create_status: {cfg.get('expected_create_status', multipart_spec.SUCCESS_CODE)}",
        f"text_field_a_name: {a['name']}",
        f"text_field_a_value: {a['value']}",
        f"text_field_b_name: {b['name']}",
        f"text_field_b_value: {b['value']}",
        f"file_field_name: {cfg['file_field']}",
        f"file_media_type: {cfg['file_media_type']}",
        f"file_size_bytes: {cfg['file_size_bytes']}",
        f"max_allowed_file_bytes: {cfg['max_allowed_file_bytes']}",
        f"readback_path: {cfg['readback_path']}",
        "contract: a multipart/form-data POST carrying the two text parts and the file "
        "part is accepted with expected_create_status, the two text fields are stored "
        "with their exact submitted values, and the response carries a non-empty "
        "document_url whose bytes (downloaded by GET) MD5-match the uploaded file; a "
        "follow-up GET of readback_path returns the two text fields; a file larger than "
        "max_allowed_file_bytes is rejected with exactly 413; omitting a required text "
        "part is rejected with exactly 400; sending the same fields as application/json "
        "is rejected with exactly 415.",
    ])


# --------------------------------------------------------------------------- #
# Multipart encoding (N text parts + one file part) — stdlib only
# --------------------------------------------------------------------------- #
def _filename_for(media_type: str) -> str:
    return {"image/png": "upload.png", "image/jpeg": "upload.jpg"}.get(media_type, "upload.bin")


def _encode_multipart(text_parts: list[tuple[str, str]],
                      file_part: tuple[str, str, str, bytes] | None) -> tuple[bytes, str]:
    """Build a multipart/form-data body. text_parts: [(name, value)]. file_part:
    (name, filename, media_type, data) or None. Returns (body_bytes, content_type)."""
    chunks: list[bytes] = []
    for name, value in text_parts:
        chunks.append(
            (f"--{_BOUNDARY}\r\n"
             f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
             f"{value}\r\n").encode())
    if file_part is not None:
        name, filename, media_type, data = file_part
        chunks.append(
            (f"--{_BOUNDARY}\r\n"
             f'Content-Disposition: form-data; name="{name}"; filename="{filename}"\r\n'
             f"Content-Type: {media_type}\r\n\r\n").encode())
        chunks.append(data)
        chunks.append(b"\r\n")
    chunks.append(f"--{_BOUNDARY}--\r\n".encode())
    return b"".join(chunks), f"multipart/form-data; boundary={_BOUNDARY}"


# --------------------------------------------------------------------------- #
# HTTP (multipart POST + JSON POST + GET) — real codes returned as-is
# --------------------------------------------------------------------------- #
def _post_multipart(path: str, method: str, body: bytes, content_type: str):
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    _assert_method(method)
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", content_type)
    req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            return r.getcode(), r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        data = b""
        try:
            data = e.read()
        except Exception:  # noqa
            pass
        return e.code, data, (e.headers.get("Content-Type") if e.headers else None)
    except Exception:  # noqa  -- connection refused/reset/timeout
        return -1, b"", None


def _post_json(path: str, method: str, payload: dict):
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    _assert_method(method)
    body = json.dumps(payload).encode()
    req = urllib.request.Request(url, data=body, method=method)
    req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), r.read()
    except urllib.error.HTTPError as e:
        data = b""
        try:
            data = e.read()
        except Exception:  # noqa
            pass
        return e.code, data
    except Exception:  # noqa
        return -1, b""


def _get(path_or_url: str):
    url = path_or_url if path_or_url.startswith("http") else f"{TARGET_BASE_URL}{path_or_url}"
    _assert_local_target(url)
    _assert_method("GET")
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        return e.code, b"", (e.headers.get("Content-Type") if e.headers else None)
    except Exception:  # noqa
        return -1, b"", None


# --------------------------------------------------------------------------- #
# Body helpers
# --------------------------------------------------------------------------- #
def _json_or_none(body: bytes):
    try:
        return json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa
        return None


def _field_token(body_obj, name: str, expected_value: str) -> str:
    """'exact' if body[name] equals the submitted value, 'mismatch' if present but
    different, 'absent' if the field is not in the response object."""
    if not isinstance(body_obj, dict) or name not in body_obj:
        return "absent"
    return "exact" if str(body_obj.get(name)) == str(expected_value) else "mismatch"


def _document_url(body_obj):
    if not isinstance(body_obj, dict):
        return None
    for k in _DOC_URL_KEYS:
        v = body_obj.get(k)
        if isinstance(v, str) and v.strip():
            return v
    return None


def _msg_refs_field(body: bytes, field_name: str) -> bool:
    try:
        text = body.decode("utf-8", "replace")
    except Exception:  # noqa
        return False
    obj = _json_or_none(body)
    msg = obj.get("message") if isinstance(obj, dict) else None
    hay = (msg if isinstance(msg, str) else text) or ""
    return field_name.lower() in hay.lower()


# --------------------------------------------------------------------------- #
# Execute the AGENT's plan (tolerant of missing/malformed keys)
# --------------------------------------------------------------------------- #
def _safe_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def _exec_plan(cfg: dict, plan: dict) -> tuple[dict, list]:
    reqlog: list = []
    obs = {"create": {"ran": False}, "download": {"ran": False},
           "readback": {"ran": False}, "oversized": {"ran": False},
           "missing_field": {"ran": False}, "wrong_ctype": {"ran": False}}
    if not isinstance(plan, dict):
        return obs, reqlog

    endpoint = plan.get("endpoint") or cfg["endpoint"]
    method = plan.get("method") or cfg["method"]
    if method not in ("POST", "PUT"):
        method = "POST"
    readback_path = plan.get("readback_path") or cfg["readback_path"]

    tfs = plan.get("text_fields") if isinstance(plan.get("text_fields"), list) else []
    text_parts = [(str(t.get("name")), str(t.get("value")))
                  for t in tfs if isinstance(t, dict) and t.get("name") is not None]

    ff = plan.get("file_field") if isinstance(plan.get("file_field"), dict) else {}
    file_name = ff.get("name") or "file"
    media_type = ff.get("media_type") or "application/octet-stream"
    file_size = _safe_int(ff.get("size_bytes"))
    max_allowed = _safe_int(plan.get("max_allowed_file_bytes"))

    planned = {c.get("label") for c in plan.get("cases", [])
               if isinstance(c, dict) and "label" in c}

    def wants(*labels) -> bool:
        return any(lbl in planned for lbl in labels)

    # ---- VALID CREATE (drives create_status / text_*_exact / document_url / readback) #
    create_body_obj = None
    returned_id = None
    original_md5 = None
    document_url = None
    if wants("create_status", "text_field_a_exact", "text_field_b_exact",
             "document_url_present", "file_md5_roundtrip", "persisted_readback") \
            and file_size is not None and 0 <= file_size <= MAX_FILE_BYTES:
        png = multipart_spec.png_bytes(file_size)
        original_md5 = multipart_spec.md5_hex(png)
        file_part = (file_name, _filename_for(media_type), media_type, png)
        body, ct = _encode_multipart(text_parts, file_part)
        status, resp, _rct = _post_multipart(endpoint, method, body, ct)
        create_body_obj = _json_or_none(resp)
        document_url = _document_url(create_body_obj)
        if isinstance(create_body_obj, dict):
            returned_id = create_body_obj.get("id")
        ta = text_parts[0] if len(text_parts) >= 1 else (None, None)
        tb = text_parts[1] if len(text_parts) >= 2 else (None, None)
        obs["create"] = {
            "ran": True, "status": status,
            "text_a": _field_token(create_body_obj, ta[0], ta[1]) if ta[0] else "absent",
            "text_b": _field_token(create_body_obj, tb[0], tb[1]) if tb[0] else "absent",
            "document_url_present": bool(document_url),
        }
        reqlog.append({"case": "valid_create", "endpoint": endpoint, "method": method,
                       "content_type": "multipart/form-data", "parts": [t[0] for t in text_parts] + [file_name],
                       "file_size_bytes": file_size, "status": status,
                       "text_a": obs["create"]["text_a"], "text_b": obs["create"]["text_b"],
                       "document_url": document_url, "returned_id": returned_id,
                       "original_md5": original_md5})

    # ---- FILE MD5 ROUND-TRIP ------------------------------------------------ #
    if wants("file_md5_roundtrip"):
        if document_url:
            d_status, d_body, _d_ct = _get(document_url)
            dl_md5 = multipart_spec.md5_hex(d_body) if d_body else None
            match = (dl_md5 is not None and original_md5 is not None and dl_md5 == original_md5)
            obs["download"] = {"ran": True, "no_url": False, "md5_match": match}
            reqlog.append({"case": "file_md5_roundtrip", "url": document_url, "status": d_status,
                           "original_md5": original_md5, "downloaded_md5": dl_md5, "md5_match": match})
        else:
            obs["download"] = {"ran": True, "no_url": True, "md5_match": None}
            reqlog.append({"case": "file_md5_roundtrip", "skipped": True,
                           "reason": "create response carried no document_url"})

    # ---- PERSISTED READBACK ------------------------------------------------- #
    if wants("persisted_readback"):
        if returned_id is not None and "{id}" in readback_path:
            rb_path = readback_path.replace("{id}", str(returned_id))
            r_status, r_body, _r_ct = _get(rb_path)
            r_obj = _json_or_none(r_body)
            a = text_parts[0] if len(text_parts) >= 1 else (None, None)
            b = text_parts[1] if len(text_parts) >= 2 else (None, None)
            persisted = bool(isinstance(r_obj, dict) and a[0] in r_obj and b[0] in r_obj
                             and str(r_obj.get(a[0])) == str(a[1]))
            obs["readback"] = {"ran": True, "persisted": persisted}
            reqlog.append({"case": "persisted_readback", "path": rb_path, "status": r_status,
                           "persisted": persisted})
        else:
            obs["readback"] = {"ran": True, "persisted": False}
            reqlog.append({"case": "persisted_readback", "skipped": True,
                           "reason": "no id returned by create or readback_path lacks {id}"})

    # ---- OVERSIZED (max_allowed_file_bytes + 1) ----------------------------- #
    if wants("oversized_rejected") and max_allowed is not None:
        big = max_allowed + 1
        if 0 < big <= MAX_FILE_BYTES:
            png = multipart_spec.png_bytes(big)
            body, ct = _encode_multipart(text_parts, (file_name, _filename_for(media_type), media_type, png))
            status, _resp, _rct = _post_multipart(endpoint, method, body, ct)
            obs["oversized"] = {"ran": True, "status": status}
            reqlog.append({"case": "oversized_rejected", "file_size_bytes": big, "status": status})
        else:
            reqlog.append({"case": "oversized_rejected", "skipped": True,
                           "reason": f"max_allowed_file_bytes+1={big} exceeds harness cap"})

    # ---- MISSING REQUIRED FIELD (omit the first text part) ------------------ #
    if wants("missing_required_field") and file_size is not None and 0 <= file_size <= MAX_FILE_BYTES:
        omitted_name = text_parts[0][0] if text_parts else None
        remaining = text_parts[1:] if len(text_parts) > 1 else []
        png = multipart_spec.png_bytes(file_size)
        body, ct = _encode_multipart(remaining, (file_name, _filename_for(media_type), media_type, png))
        status, resp, _rct = _post_multipart(endpoint, method, body, ct)
        refs = _msg_refs_field(resp, omitted_name) if omitted_name else False
        obs["missing_field"] = {"ran": True, "status": status, "msg_refs_field": refs}
        reqlog.append({"case": "missing_required_field", "omitted_field": omitted_name,
                       "status": status, "msg_refs_field": refs})

    # ---- WRONG CONTENT-TYPE (same fields as application/json) --------------- #
    if wants("wrong_content_type"):
        payload = {name: value for name, value in text_parts}
        status, _resp = _post_json(endpoint, method, payload)
        obs["wrong_ctype"] = {"ran": True, "status": status}
        reqlog.append({"case": "wrong_content_type", "content_type": "application/json",
                       "status": status})

    return obs, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
    import time
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# Headline QA rate (a property of the TARGET, not the agent)
# --------------------------------------------------------------------------- #
def _multipart_accuracy(all_cases: list) -> tuple[int, int]:
    """Multipart Handling Accuracy = correct scenarios / total, across all endpoints.
    'correct' means the live API matched the idealized multipart contract token."""
    total = correct = 0
    for case in all_cases:
        for s in case["scenarios"]:
            total += 1
            correct += 1 if s["api_correct"] else 0
    return correct, total


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_multipart_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the multipart plan object (see multipart_spec): a dict with
        endpoint/method/text_fields/file_field/max_allowed_file_bytes/readback_path and a
        nine-entry `cases` list. The harness builds the exact bodies, executes the planned
        requests against the one local target, evaluates every scenario, and records.
        Whatever the agent fails to plan scores as 'missing'. generate may raise; recorded.
    """
    cfgs = endpoint_cfgs()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        raw, reqlog = _exec_plan(cfg, plan)
        observed = multipart_spec.evaluate(raw)

        scenarios = []
        for label in multipart_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = multipart_spec.correct(label, tok, cfg)
            scenarios.append({"endpoint": cfg["endpoint"], "scenario": label,
                              "ideal": multipart_spec.ideal_for(label, cfg),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"slug": cfg.get("slug"), "endpoint": cfg["endpoint"],
                          "method": cfg.get("method"), "emitted_plan": plan,
                          "request_log": reqlog, "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "multipart_handling_accuracy_pct": rate,
               "scenarios_total": total, "scenarios_api_correct": correct,
               "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "multipart_handling_accuracy_pct": rate, "scenarios_total": total})
    everos_note(agent, f"multipart-form-data run: accuracy={rate}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Multipart Handling Accuracy; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-multipart-form-data-handling" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "multipart_handling_accuracy_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
    import re
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # noqa
        return None

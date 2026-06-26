"""Shared, deterministic plumbing for the four file-upload-and-download-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the upload-endpoint catalogue from
    data/test-file-upload-and-download/upload_spec.json
  - build the compact per-endpoint contract brief handed to the agent
  - execute whatever plan the agent emitted: for each "uploads" entry, build the EXACT
    -sized file in memory (upload_spec.file_bytes), record its MD5, multipart-POST it to
    the LOCAL target, and record the real status + whether the response carried a "url";
    for each "downloads" entry, GET the URL its source upload returned, record the status
    + Content-Type, and MD5-compare the downloaded bytes to the original (host + method
    guards: localhost only, GET/POST only, file size capped)
  - evaluate every scenario (shared upload_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified. It ships no file-upload/-download endpoint,
so a multipart POST to any documented upload path matches no route and returns 404 with
no "url" — the legitimate QA finding (mirroring test-rate-limit-enforcement's absent
limiter). DummyJSON also simulates writes without persisting, so these POSTs change no
server state; we never edit DummyJSON's code or data.

The framework-specific part — turning one endpoint's brief into the upload/download test
plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
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
SPEC_PATH = WORKSPACE / "data" / "test-file-upload-and-download" / "upload_spec.json"

# Safety cap so a malformed plan can never make the harness allocate a huge file or
# push a huge body at the target. Legitimate plans top out at max_size_bytes + 1.
MAX_FILE_BYTES = 16 * 1024 * 1024  # 16 MiB
_MULTIPART_BOUNDARY = "forgeFileUploadBoundary7MA4YWxkTrZu0gW"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import upload_spec  # noqa: E402


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
    if method not in ("GET", "POST"):
        raise PermissionError(f"refusing method {method}: only GET (download) and POST (upload) allowed")


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = []
    for e in spec["endpoints"]:
        out.append({
            "upload_endpoint": e["upload_endpoint"],
            "max_size_bytes": e.get("max_size_bytes", spec.get("max_size_bytes", upload_spec.DEFAULT_MAX_SIZE_BYTES)),
            "allowed_mime_types": e.get("allowed_mime_types", spec.get("allowed_mime_types", upload_spec.DEFAULT_ALLOWED_MIME_TYPES)),
            "success_code": e.get("success_code", spec.get("success_code", upload_spec.SUCCESS_CODE)),
            "over_size_code": e.get("over_size_code", spec.get("over_size_code", upload_spec.OVER_SIZE_CODE)),
            "invalid_mime_code": e.get("invalid_mime_code", spec.get("invalid_mime_code", upload_spec.INVALID_MIME_CODE)),
            "download_success_code": e.get("download_success_code", spec.get("download_success_code", upload_spec.DOWNLOAD_SUCCESS_CODE)),
        })
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["upload_endpoint"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous upload contract handed to the LLM."""
    return "\n".join([
        f"upload_endpoint: {cfg['upload_endpoint']}",
        f"max_size_bytes: {cfg['max_size_bytes']}        # documented maximum accepted file size in bytes",
        f"allowed_mime_types: {json.dumps(cfg['allowed_mime_types'])}   # MIME types the endpoint accepts",
        f"success_code: {cfg['success_code']}            # status an accepted upload returns",
        f"over_size_code: {cfg['over_size_code']}          # status an over-maximum upload returns",
        f"invalid_mime_code: {cfg['invalid_mime_code']}       # status a disallowed-MIME upload returns",
        f"download_success_code: {cfg['download_success_code']}   # status a successful download returns",
        "contract: a file up to max_size_bytes of an allowed MIME type is accepted with success_code and a "
        "response 'url'; a file of max_size_bytes+1 is rejected with over_size_code and no 'url'; a "
        "disallowed-MIME file is rejected with invalid_mime_code and no 'url'; each accepted file is "
        "downloadable at its 'url' with download_success_code, Content-Type image/jpeg, and bytes identical "
        "to what was uploaded.",
    ])


# --------------------------------------------------------------------------- #
# HTTP (multipart POST upload + GET download)
# --------------------------------------------------------------------------- #
def _filename_for(mime: str) -> str:
    if mime == "image/jpeg":
        return "upload.jpg"
    if mime == "image/png":
        return "upload.png"
    if mime == "application/octet-stream":
        return "upload.exe"
    return "upload.bin"


def _multipart(field: str, filename: str, mime: str, data: bytes) -> tuple[bytes, str]:
    pre = (f"--{_MULTIPART_BOUNDARY}\r\n"
           f'Content-Disposition: form-data; name="{field}"; filename="{filename}"\r\n'
           f"Content-Type: {mime}\r\n\r\n").encode()
    post = f"\r\n--{_MULTIPART_BOUNDARY}--\r\n".encode()
    return pre + data + post, f"multipart/form-data; boundary={_MULTIPART_BOUNDARY}"


def _post_multipart(path: str, mime: str, data: bytes):
    """multipart/form-data POST of one file. Returns (status, body_bytes, content_type).
    A real HTTP error code (404, 413, 415, ...) is a real response, returned as-is."""
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    _assert_method("POST")
    body, ct = _multipart("file", _filename_for(mime), mime, data)
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("Content-Type", ct)
    req.add_header("Content-Length", str(len(body)))
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.getcode(), r.read(), r.headers.get("Content-Type")
    except urllib.error.HTTPError as e:
        data_b = b""
        try:
            data_b = e.read()
        except Exception:  # noqa
            pass
        return e.code, data_b, (e.headers.get("Content-Type") if e.headers else None)
    except Exception:  # noqa  -- connection refused/reset/timeout
        return -1, b"", None


def _get(path_or_url: str):
    """Read-only GET of a download URL. Returns (status, body_bytes, content_type)."""
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


def _url_in_body(body: bytes):
    """Return (has_url, url_value). A JSON object with a truthy top-level 'url' counts."""
    try:
        j = json.loads(body.decode("utf-8", "replace"))
    except Exception:  # noqa
        return False, None
    if isinstance(j, dict) and j.get("url"):
        return True, j["url"]
    return False, None


def _exec_plan(cfg: dict, plan: dict) -> tuple[dict, list]:
    """Execute the AGENT's plan with real HTTP. Tolerant of missing/malformed keys —
    whatever the agent omits is not exercised and the dependent scenarios score
    'missing'. Returns (raw_obs, request_log)."""
    reqlog: list = []
    raw = {"uploads": {}, "downloads": {}}
    if not isinstance(plan, dict):
        return raw, reqlog

    endpoint = plan.get("upload_endpoint") or cfg["upload_endpoint"]
    uploaded: dict[str, dict] = {}

    # 1. Uploads — build the exact-sized file, MD5 it, multipart-POST it.
    uploads = plan.get("uploads") if isinstance(plan.get("uploads"), list) else []
    for u in uploads:
        if not isinstance(u, dict) or "label" not in u:
            continue
        label = u["label"]
        size = u.get("size_bytes")
        mime = u.get("mime_type") or "application/octet-stream"
        try:
            size = int(size)
        except (TypeError, ValueError):
            size = None
        if size is None or size < 0 or size > MAX_FILE_BYTES:
            raw["uploads"][label] = {"ran": False, "status": None, "url_in_body": None,
                                     "guard": "missing-or-oversize size_bytes"}
            reqlog.append({"label": label, "skipped": True, "size_bytes": u.get("size_bytes")})
            continue
        data = upload_spec.file_bytes(mime, size)
        original_md5 = upload_spec.md5_hex(data)
        status, resp_body, _ct = _post_multipart(endpoint, mime, data)
        has_url, url_val = _url_in_body(resp_body)
        raw["uploads"][label] = {"ran": True, "status": status, "url_in_body": has_url}
        uploaded[label] = {"md5": original_md5, "url": url_val, "size": size, "mime": mime}
        reqlog.append({"label": label, "endpoint": endpoint, "size_bytes": size, "mime": mime,
                       "status": status, "url_in_body": has_url, "returned_url": url_val,
                       "original_md5": original_md5})

    # 2. Downloads — GET the URL the source upload returned, MD5-compare to original.
    downloads = plan.get("downloads") if isinstance(plan.get("downloads"), list) else []
    for d in downloads:
        if not isinstance(d, dict) or "label" not in d:
            continue
        label = d["label"]
        src = d.get("source")
        src_rec = uploaded.get(src)
        if not src_rec or not src_rec.get("url"):
            # No URL was returned by the source upload -> nothing to download.
            raw["downloads"][label] = {"ran": False, "status": None,
                                       "content_type": None, "md5_match": None}
            reqlog.append({"label": label, "source": src, "skipped": True,
                           "reason": "source upload returned no url"})
            continue
        status, body, ct = _get(src_rec["url"])
        dl_md5 = upload_spec.md5_hex(body) if body else None
        match = (dl_md5 is not None and dl_md5 == src_rec["md5"])
        raw["downloads"][label] = {"ran": True, "status": status,
                                   "content_type": ct, "md5_match": match}
        reqlog.append({"label": label, "source": src, "url": src_rec["url"], "status": status,
                       "content_type": ct, "original_md5": src_rec["md5"],
                       "downloaded_md5": dl_md5, "md5_match": match})

    return raw, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(_now_epoch())}],
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


def _now_epoch() -> float:
    import time
    return time.time()


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# Rates (the task's headline QA finding about the target API)
# --------------------------------------------------------------------------- #
def _rates(all_cases: list) -> dict:
    """The three task rates, computed across all upload endpoints. These describe the
    TARGET (DummyJSON), not the agent: against an unimplemented upload endpoint each is
    0% and the gap is the QA finding."""
    integ_num = integ_den = 0
    over_num = over_den = 0
    mime_num = mime_den = 0
    for case in all_cases:
        ev = {s["scenario"]: s["observed_token"] for s in case["scenarios"]}
        for scn in ("download_1kb_md5_match", "download_max_md5_match"):
            if ev.get(scn) != "missing":
                integ_den += 1
                if ev.get(scn) == "true":
                    integ_num += 1
        if ev.get("upload_over_status") != "missing":
            over_den += 1
            if ev.get("upload_over_status") == "413":
                over_num += 1
        if ev.get("upload_invalid_status") != "missing":
            mime_den += 1
            if ev.get("upload_invalid_status") == "415":
                mime_num += 1
    pct = lambda n, d: round(100.0 * n / d, 2) if d else 0.0
    return {
        "file_integrity_rate_pct": pct(integ_num, integ_den),
        "over_size_rejection_rate_pct": pct(over_num, over_den),
        "invalid_mime_rejection_rate_pct": pct(mime_num, mime_den),
        "file_integrity_basis": f"{integ_num}/{integ_den}",
        "over_size_basis": f"{over_num}/{over_den}",
        "invalid_mime_basis": f"{mime_num}/{mime_den}",
    }


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_upload_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the upload/download plan object (see upload_spec): a dict
        with `uploads` (four {label,size_bytes,mime_type,expect_code,expect_url}) and
        `downloads` (two {label,source,expect_code,expect_content_type_prefix,
        expect_md5_match}). The harness builds the exact files, executes the planned
        requests, MD5-compares, and evaluates every scenario. Whatever the agent fails
        to emit scores as 'missing'. generate may raise; recorded per-endpoint.
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
        observed = upload_spec.evaluate(raw)

        scenarios = []
        for label in upload_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = upload_spec.correct(label, tok, cfg)
            scenarios.append({"endpoint": cfg["upload_endpoint"], "scenario": label,
                              "ideal": upload_spec.ideal_for(label, cfg),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"endpoint": cfg["upload_endpoint"],
                          "max_size_bytes": cfg["max_size_bytes"],
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    rates = _rates(all_cases)
    overall_pass = (rates["file_integrity_rate_pct"] == 100.0
                    and rates["over_size_rejection_rate_pct"] == 100.0
                    and rates["invalid_mime_rejection_rate_pct"] == 100.0)
    raw_doc = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
               "upload_contract_correctness_rate_pct": rate,
               "file_integrity_rate_pct": rates["file_integrity_rate_pct"],
               "over_size_rejection_rate_pct": rates["over_size_rejection_rate_pct"],
               "invalid_mime_rejection_rate_pct": rates["invalid_mime_rejection_rate_pct"],
               "rates_basis": {k: rates[k] for k in
                               ("file_integrity_basis", "over_size_basis", "invalid_mime_basis")},
               "overall_pass": overall_pass,
               "scenarios_total": total, "scenarios_api_correct": correct,
               "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "upload_contract_correctness_rate_pct": rate,
        "file_integrity_rate_pct": rates["file_integrity_rate_pct"],
        "over_size_rejection_rate_pct": rates["over_size_rejection_rate_pct"],
        "invalid_mime_rejection_rate_pct": rates["invalid_mime_rejection_rate_pct"],
        "overall_pass": overall_pass, "scenarios_total": total})

    everos_note(agent, f"file-upload-download run: correctness_rate={rate}% "
                       f"integrity={rates['file_integrity_rate_pct']}% "
                       f"over413={rates['over_size_rejection_rate_pct']}% "
                       f"invalid415={rates['invalid_mime_rejection_rate_pct']}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    contract-correctness rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-file-upload-and-download" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "upload_contract_correctness_rate_pct"),
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

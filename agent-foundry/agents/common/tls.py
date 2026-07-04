"""Shared, deterministic plumbing for the four SSL/TLS-enforcement-testing agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines). It is
the identical substrate every framework sits on, so leaderboard differences are
attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the TLS contract from data/test-ssl-tls-enforcement/tls_spec.json
  - build the compact target brief handed to the agent
  - execute whatever plan the agent emitted with handshake + READ-ONLY GET probes
    against the ONE configured target (host allowlist guard): plain HTTP, the four TLS
    version handshakes, the certificate fields, and the forbidden-weak-cipher families,
    using openssl + curl + Python ssl as the DETERMINISTIC primary, with testssl.sh and
    sslyze run once for recorded enrichment/cross-check (best-effort, non-fatal)
  - evaluate every scenario (shared tls_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

The target is a LOCAL, air-gapped TLS fixture in front of an UNMODIFIED DummyJSON: only
handshakes and read-only GETs are performed; nothing mutates the target.

The framework-specific part — turning the target brief into the TLS test plan via the
backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import socket
import ssl
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
SPEC_PATH = WORKSPACE / "data" / "test-ssl-tls-enforcement" / "tls_spec.json"
# Unique per-process token so the four agents (run in parallel under ONE run-id) never
# collide on a shared temp file (leaf cert / testssl / sslyze scratch).
_UNIQ = f"{os.getpid()}-{os.environ.get('FORGE_AGENT', 'agent')}"

# Only these hosts may ever be contacted — the one local fixture. Everything else is refused.
ALLOWED_HOSTS = {"localhost", "127.0.0.1", "::1", "dummyjson.local"}
# Per-command wall-clock cap so a probe can never hang the run.
CMD_TIMEOUT = 25
TESTSSL_TIMEOUT = 200

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import tls_spec  # noqa: E402


# --------------------------------------------------------------------------- #
# Guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_allowed_host(host: str) -> None:
    if host not in ALLOWED_HOSTS:
        raise PermissionError(f"refusing non-allowlisted TLS target: {host}")


def _run(cmd: list[str], timeout: int = CMD_TIMEOUT, stdin: str | None = None) -> tuple[int, str]:
    """Run a probe command, returning (exit_code, combined_output). Never raises on
    a non-zero exit (a failed handshake IS the signal); only times out defensively."""
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout,
                           input=stdin)
        return p.returncode, (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return -2, "TIMEOUT"
    except FileNotFoundError:
        return -3, "NOT_FOUND"


# --------------------------------------------------------------------------- #
# G1 staging write
# --------------------------------------------------------------------------- #
def _write_staging_findings(
    agent: str,
    item_id: str,
    item_label: str,
    step_results: list[dict],
) -> None:
    """Write per-item step findings to the G1 staging directory.

    Path: results/runs/{RUN_ID}/staging/{agent}/{item_id}-findings.json

    Called once per item (endpoint / collection / scenario) after all steps
    for that item are complete. The G1b orchestration step reads these files
    and passes them to test-case-creator as evidence of what this agent observed.
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"
    _assert_sandbox(out_path)

    findings = []
    for i, r in enumerate(step_results, start=1):
        findings.append({
            "step_number": i,
            "item_id": item_id,
            "item_label": item_label,
            **r,
        })

    out_path.write_text(json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def target_cfg() -> dict:
    spec = load_spec()
    t = spec["target"]
    return {
        "target_host": t["host"],
        "target_port": int(t["tls_port"]),
        "http_port": int(t["http_port"]),
        "endpoint_path": t["endpoint_path"],
        "ca_bundle": str((WORKSPACE / t["ca_bundle"]).resolve()),
        "documented_min_tls": spec.get("documented_min_tls", "1.2"),
    }


def target_brief(cfg: dict) -> str:
    """Compact, unambiguous TLS-enforcement contract handed to the LLM."""
    return "\n".join([
        f"target_host: {cfg['target_host']}",
        f"target_port: {cfg['target_port']}        # the HTTPS/TLS port",
        f"http_port: {cfg['http_port']}            # the plaintext-HTTP port",
        f"endpoint_path: {cfg['endpoint_path']}    # a read-only GET endpoint",
        f"documented_min_tls: {cfg['documented_min_tls']}   # minimum TLS version the API must require",
        "contract: plain HTTP must be refused or redirected to HTTPS and return no API "
        "data; TLS 1.0 and TLS 1.1 must be refused; TLS 1.2 and TLS 1.3 must be accepted "
        "and serve the endpoint; the certificate must be non-expired, CN/SAN-matched to "
        "the host, signed by a trusted CA (chain of trust ok), and not self-signed; and "
        "no weak cipher suite (RC4, DES, 3DES, EXPORT, NULL) may be offered.",
    ])


# --------------------------------------------------------------------------- #
# Deterministic probes (openssl / curl / Python ssl)
# --------------------------------------------------------------------------- #
_OPENSSL_VER_FLAG = {"tls1": "-tls1", "tls1_1": "-tls1_1", "tls1_2": "-tls1_2", "tls1_3": "-tls1_3"}
_PY_TLS_VER = {"tls1_2": ssl.TLSVersion.TLSv1_2, "tls1_3": ssl.TLSVersion.TLSv1_3}
_ACCEPT_RE = re.compile(r"Cipher\s+is\s+(?!\(NONE\))\S", re.IGNORECASE)
_REFUSE_RE = re.compile(r"no protocols available|handshake failure|alert |"
                        r"ssl_choose_client_version|wrong version|connection reset|"
                        r"no ciphers available|unsupported protocol", re.IGNORECASE)


def _plain_http(cfg: dict) -> tuple[int | None, bool | None]:
    """GET over plaintext HTTP WITHOUT following redirects. Returns (status, returned_json).
    A 3xx (redirect) or a connection refusal is the enforced behavior; a 200 carrying a
    JSON body is the failure (data over plaintext)."""
    host, port, path = cfg["target_host"], cfg["http_port"], cfg["endpoint_path"]
    _assert_allowed_host(host)
    url = f"http://{host}:{port}{path}"

    class _NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None

    opener = urllib.request.build_opener(_NoRedirect)
    try:
        with opener.open(url, timeout=CMD_TIMEOUT) as r:
            body = r.read()
            status = r.getcode()
    except urllib.error.HTTPError as e:
        body = e.read() if e.fp else b""
        status = e.code
    except Exception:  # noqa  -- connection refused/reset
        return -1, False
    returned_json = False
    if body:
        try:
            json.loads(body)
            returned_json = True
        except Exception:  # noqa
            returned_json = False
    return status, returned_json


def _handshake(cfg: dict, version: str) -> str | None:
    """openssl s_client handshake at a fixed TLS version. Returns 'accepted', 'refused',
    or None on an inconclusive/timeout result."""
    host, port = cfg["target_host"], cfg["target_port"]
    _assert_allowed_host(host)
    flag = _OPENSSL_VER_FLAG.get(version)
    if not flag:
        return None
    code, out = _run(["openssl", "s_client", "-connect", f"{host}:{port}",
                      "-servername", host, flag], stdin="")
    if _ACCEPT_RE.search(out):
        return "accepted"
    if code != 0 or _REFUSE_RE.search(out):
        return "refused"
    return None


def _https_get_pinned(cfg: dict, version: str) -> int | None:
    """HTTP status of a GET forced over exactly TLS 1.2 or 1.3. Tries curl first (literal
    to the documented 'How'); falls back to Python ssl with the version pinned (reliable
    even where the curl build lacks --tlsv1.3)."""
    host, port, path = cfg["target_host"], cfg["target_port"], cfg["endpoint_path"]
    _assert_allowed_host(host)
    ca = cfg["ca_bundle"]
    curl_flag = {"tls1_2": ["--tlsv1.2", "--tls-max", "1.2"], "tls1_3": ["--tlsv1.3"]}.get(version)
    if curl_flag and shutil.which("curl"):
        code, out = _run(["curl", "-sS", "--cacert", ca, *curl_flag, "-o", "/dev/null",
                          "-w", "%{http_code}", f"https://{host}:{port}{path}"])
        m = re.search(r"\b([1-5]\d\d)\b", out)
        if code == 0 and m:
            return int(m.group(1))
    # Fallback: Python ssl with the version pinned.
    pv = _PY_TLS_VER.get(version)
    if pv is None:
        return None
    ctx = ssl.create_default_context(cafile=ca)
    ctx.minimum_version = ctx.maximum_version = pv
    try:
        with socket.create_connection((host, port), timeout=CMD_TIMEOUT) as sock:
            with ctx.wrap_socket(sock, server_hostname=host) as ss:
                req = (f"GET {path} HTTP/1.1\r\nHost: {host}\r\n"
                       "Connection: close\r\n\r\n").encode()
                ss.sendall(req)
                head = b""
                while b"\r\n" not in head:
                    chunk = ss.recv(256)
                    if not chunk:
                        break
                    head += chunk
        m = re.match(rb"HTTP/1\.[01]\s+(\d{3})", head)
        return int(m.group(1)) if m else None
    except Exception:  # noqa
        return None


def _fetch_leaf_pem(cfg: dict) -> str | None:
    host, port = cfg["target_host"], cfg["target_port"]
    code, out = _run(["openssl", "s_client", "-connect", f"{host}:{port}",
                      "-servername", host, "-showcerts"], stdin="")
    m = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", out, re.DOTALL)
    return m.group(0) if m else None


def _cert_probes(cfg: dict, wanted: set[str]) -> dict:
    """Measure the requested certificate assertions. Returns a dict with True/False/None
    per requested key (None => not requested by the plan => scored 'missing')."""
    out: dict[str, bool | None] = {k: None for k in tls_spec.CERT_ASSERTIONS}
    if not wanted:
        return out
    pem = _fetch_leaf_pem(cfg)
    if not pem:
        return out
    tmp = WORKSPACE / "results" / "runs" / RUN_ID / f"_leaf-{_UNIQ}.pem"
    tmp.parent.mkdir(parents=True, exist_ok=True)
    _assert_sandbox(tmp)
    tmp.write_text(pem)

    _, text = _run(["openssl", "x509", "-in", str(tmp), "-noout",
                    "-subject", "-issuer", "-enddate", "-ext", "subjectAltName"])
    subject = re.search(r"subject=(.*)", text)
    issuer = re.search(r"issuer=(.*)", text)
    enddate = re.search(r"notAfter=(.*)", text)
    san = re.search(r"DNS:[^\n]*|IP Address:[^\n]*", text)

    if "not_expired" in wanted and enddate:
        # openssl -checkend 0: exit 0 => NOT expired within 0 seconds (still valid).
        code, _ = _run(["openssl", "x509", "-in", str(tmp), "-noout", "-checkend", "0"])
        out["not_expired"] = (code == 0)

    if "cn_or_san_match" in wanted:
        host = cfg["target_host"]
        cn = ""
        if subject:
            cnm = re.search(r"CN\s*=\s*([^,/\n]+)", subject.group(1))
            cn = cnm.group(1).strip() if cnm else ""
        san_text = san.group(0) if san else ""
        out["cn_or_san_match"] = (host == cn) or (host in san_text)

    if "chain_of_trust_ok" in wanted:
        # Verify the leaf against the fixture's own CA bundle (a real CA it controls).
        code, vout = _run(["openssl", "verify", "-CAfile", cfg["ca_bundle"], str(tmp)])
        out["chain_of_trust_ok"] = (code == 0 and "OK" in vout)

    if "not_self_signed" in wanted and subject and issuer:
        out["not_self_signed"] = (subject.group(1).strip() != issuer.group(1).strip())

    tmp.unlink(missing_ok=True)
    return out


def _weak_cipher_offered(cfg: dict, family: str) -> bool | None:
    """Does the server OFFER a cipher of this forbidden family? True=offered (bad),
    False=not offered (good), None=inconclusive. Forces an openssl handshake limited to
    the family's cipher spec; a successful 'Cipher is' means it negotiated."""
    host, port = cfg["target_host"], cfg["target_port"]
    spec_map = {
        "RC4": "RC4", "DES": "DES:!3DES", "3DES": "3DES:DES-CBC3-SHA",
        "EXPORT": "EXPORT", "NULL": "NULL:eNULL:aNULL",
    }
    cipher = spec_map.get(family)
    if cipher is None:
        return None
    # @SECLEVEL=0 lets openssl even propose obsolete suites if it still has them.
    code, out = _run(["openssl", "s_client", "-connect", f"{host}:{port}",
                      "-servername", host, "-tls1_2",
                      "-cipher", f"{cipher}:@SECLEVEL=0"], stdin="")
    if _ACCEPT_RE.search(out):
        return True   # the server negotiated a weak cipher — a real failure
    # "no cipher match"/handshake failure/refused => the family was not negotiable => not offered
    return False


# --------------------------------------------------------------------------- #
# Enrichment: testssl.sh + sslyze (best-effort, recorded, non-fatal)
# --------------------------------------------------------------------------- #
def _testssl_enrichment(cfg: dict) -> dict:
    bin_ = shutil.which("testssl.sh") or shutil.which("testssl")
    if not bin_:
        return {"available": False}
    jf = WORKSPACE / "results" / "runs" / RUN_ID / f"_testssl-{_UNIQ}.json"
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.unlink(missing_ok=True)  # testssl APPENDS — always start fresh
    code, _ = _run([bin_, "--quiet", "--color", "0", "--jsonfile", str(jf),
                    "--protocols", "--server-defaults", "--std",
                    f"{cfg['target_host']}:{cfg['target_port']}"], timeout=TESTSSL_TIMEOUT)
    findings = {}
    try:
        for r in json.loads(jf.read_text()):
            i = r.get("id", "")
            if i in ("TLS1", "TLS1_1", "TLS1_2", "TLS1_3", "cert_trust",
                     "cert_chain_of_trust", "cert_expirationStatus", "cert_commonName",
                     "cert_subjectAltName", "cert_caIssuers",
                     "cipherlist_NULL", "cipherlist_aNULL", "cipherlist_EXPORT",
                     "cipherlist_LOW", "cipherlist_3DES_IDEA"):
                findings[i] = {"severity": r.get("severity"), "finding": r.get("finding")}
    except Exception:  # noqa
        pass
    jf.unlink(missing_ok=True)
    return {"available": True, "exit": code, "findings": findings}


def _sslyze_enrichment(cfg: dict) -> dict:
    bin_ = shutil.which("sslyze")
    if not bin_:
        return {"available": False}
    jf = WORKSPACE / "results" / "runs" / RUN_ID / f"_sslyze-{_UNIQ}.json"
    jf.parent.mkdir(parents=True, exist_ok=True)
    jf.unlink(missing_ok=True)
    code, _ = _run([bin_, "--certinfo", "--tlsv1_2", "--tlsv1_3", "--sslv3", "--tlsv1",
                    "--tlsv1_1", "--json_out", str(jf),
                    f"{cfg['target_host']}:{cfg['target_port']}"], timeout=TESTSSL_TIMEOUT)
    summary = {}
    try:
        d = json.loads(jf.read_text())
        res = (d.get("server_scan_results") or [{}])[0].get("scan_result", {})
        for proto in ("ssl_2_0_cipher_suites", "ssl_3_0_cipher_suites",
                      "tls_1_0_cipher_suites", "tls_1_1_cipher_suites",
                      "tls_1_2_cipher_suites", "tls_1_3_cipher_suites"):
            node = (res.get(proto) or {}).get("result", {})
            accepted = node.get("accepted_cipher_suites")
            if accepted is not None:
                summary[proto] = len(accepted)
    except Exception:  # noqa
        pass
    jf.unlink(missing_ok=True)
    return {"available": True, "exit": code, "accepted_suite_counts": summary}


# --------------------------------------------------------------------------- #
# Plan execution
# --------------------------------------------------------------------------- #
def _exec_plan(cfg: dict, plan: dict) -> tuple[dict, list]:
    """Execute the AGENT's plan (handshake + read-only GET) deterministically. Tolerant
    of missing/malformed keys: whatever the agent omits is not probed and its scenarios
    score 'missing'. Returns (raw_obs, request_log)."""
    raw: dict = {
        "http_status": None, "http_returned_json": None,
        "tls1_0": None, "tls1_1": None, "tls1_2": None, "tls1_3": None,
        "tls1_2_http": None, "tls1_3_http": None,
        "cert_not_expired": None, "cert_cn_or_san_match": None,
        "cert_chain_of_trust_ok": None, "cert_not_self_signed": None,
        "weak_offered": {},
    }
    reqlog: list = []
    if not isinstance(plan, dict):
        return raw, reqlog

    probes = plan.get("protocol_probes") if isinstance(plan.get("protocol_probes"), list) else []
    labels = {p.get("label") for p in probes if isinstance(p, dict)}

    if "plain_http" in labels:
        st, rj = _plain_http(cfg)
        raw["http_status"], raw["http_returned_json"] = st, rj
        reqlog.append({"probe": "plain_http", "status": st, "returned_json": rj})

    for label, ver in (("tls1_0", "tls1"), ("tls1_1", "tls1_1"),
                       ("tls1_2", "tls1_2"), ("tls1_3", "tls1_3")):
        if label in labels:
            res = _handshake(cfg, ver)
            raw[label] = res
            reqlog.append({"probe": label, "handshake": res})

    if "tls1_2" in labels:
        raw["tls1_2_http"] = _https_get_pinned(cfg, "tls1_2")
        reqlog.append({"probe": "tls1_2_http", "status": raw["tls1_2_http"]})
    if "tls1_3" in labels:
        raw["tls1_3_http"] = _https_get_pinned(cfg, "tls1_3")
        reqlog.append({"probe": "tls1_3_http", "status": raw["tls1_3_http"]})

    # Only string assertion names are valid probe keys; a plan that emits dict-shaped
    # or otherwise non-string entries is tolerated (skipped) rather than crashing the
    # harness on an unhashable value (robustness / adversarial-input lens).
    wanted_cert = {a for a in (plan.get("certificate_assertions") or []) if isinstance(a, str)}
    cert = _cert_probes(cfg, wanted_cert)
    for k in tls_spec.CERT_ASSERTIONS:
        raw[f"cert_{k}"] = cert.get(k)
    if wanted_cert:
        # cert.get(k): a requested field the served cert does not expose degrades to
        # None rather than raising KeyError (degrade to the observable signal).
        reqlog.append({"probe": "certificate", "assertions": sorted(wanted_cert),
                       "result": {k: cert.get(k) for k in wanted_cert}})

    for fam in (plan.get("forbidden_weak_ciphers") or []):
        if fam in tls_spec.WEAK_CIPHER_SCENARIO:
            offered = _weak_cipher_offered(cfg, fam)
            raw["weak_offered"][fam] = offered
            reqlog.append({"probe": f"weak_cipher_{fam}", "offered": offered})

    return raw, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


def everos_note(agent: str, text: str) -> None:
    import time
    cfg = _config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        body = json.dumps(payload).encode()
        req = urllib.request.Request(base + "/api/v1/memory/add", data=body,
                                     headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_tls_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the TLS test plan object (see tls_spec): a dict with
        target_host/target_port/http_port/endpoint_path, protocol_probes, the cert
        assertions list, and the forbidden_weak_ciphers list. The harness executes the
        AGENT's planned probes deterministically and evaluates every scenario. Whatever
        the agent fails to emit scores as 'missing'. generate may raise; recorded.
    """
    cfg = target_cfg()
    try:
        plan = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    raw, reqlog = _exec_plan(cfg, plan)
    observed = tls_spec.evaluate(raw)

    enrichment = {"testssl": _testssl_enrichment(cfg), "sslyze": _sslyze_enrichment(cfg)}

    scenarios = []
    total = correct = 0
    for label in tls_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = tls_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": tls_spec.ideal_for(label),
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    # G1 staging write — write per-item findings for G1b orchestration
    _write_staging_findings(
        agent=agent,
        item_id=f"{cfg['target_host']}-{cfg['target_port']}".replace("/", "-").replace(":", "-") or "tls-target",
        item_label=f"https://{cfg['target_host']}:{cfg['target_port']}",
        step_results=[
            {
                "assertion_result": "PASS" if s.get("api_correct") else "FAIL",
                "assertion_detail": (
                    f"scenario={s.get('scenario')} ideal={s.get('ideal')} "
                    f"observed={s.get('observed_token')}"
                ),
                **s,
            }
            for s in scenarios
        ],
    )

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw_doc = {
        "agent": agent, "run_id": RUN_ID,
        "target": f"https://{cfg['target_host']}:{cfg['target_port']}",
        "tls_enforcement_rate_pct": rate,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "emitted_plan": plan, "raw_observations": raw, "request_log": reqlog,
        "scenarios": scenarios, "enrichment": enrichment, "error": gen_error,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw_doc, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "tls_enforcement_rate_pct": rate, "scenarios_total": total,
        "scenarios_api_correct": correct})
    everos_note(agent, f"ssl-tls-enforcement run: enforcement_rate={rate}% "
                       f"({correct}/{total} scenarios) target={raw_doc['target']}")
    return raw_doc


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline TLS
    Enforcement Rate; the judge later overwrites metric_value with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-ssl-tls-enforcement" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "tls_enforcement_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
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

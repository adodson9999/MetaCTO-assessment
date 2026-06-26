#!/usr/bin/env python3
"""Gold-set builder for the API SSL/TLS-enforcement testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it loads the
documented TLS contract (tls_spec.json), derives the canonical correct TLS test plan,
executes every probe against the LOCAL TLS fixture with the SAME shared harness the
agents use (handshake + read-only GET via openssl/curl/Python-ssl, plus testssl.sh and
sslyze enrichment), and records the REAL observed token per scenario.

The DummyJSON app is NEVER modified. The fixture (tls_fixture.py) terminates TLS in
front of the untouched DummyJSON and is the system under test. All probing is
handshake + read-only GET only.

The recorded per-scenario observed token is the ground truth. Agents are later ranked
on how faithfully their own runs reproduce this table (coverage + correct probe
construction). Where the fixture's real token differs from the idealized contract token
would be a genuine TLS-enforcement finding; the fixture is configured to enforce TLS
correctly, so the expected empirical result is a clean ~100% — a positive finding, in
contrast to the prior api-tester builds where DummyJSON failed its idealized contract.

Outputs (under data/test-ssl-tls-enforcement/):
  - gold/target.json   the per-target gold scenarios
  - gold.json          consolidated gold table + empirical enforcement-rate summary

Usage:
  python3 build_gold.py          # fixture must be up (tls_fixture.py start)
Stdlib only. No network beyond the local fixture (handshake + read-only GET). Air-gapped.
"""
import json
import os
import socket
import ssl
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"
WS = HERE.parents[1]

# Reuse the EXACT shared harness + scenario definitions (one source of truth).
os.environ.setdefault("FORGE_WORKSPACE", str(WS))
os.environ.setdefault("FORGE_SANDBOX_ROOT", str(WS))
os.environ.setdefault("FORGE_RUN_ID", "gold-build")
sys.path.insert(0, str(WS / "agents" / "common"))
import tls  # noqa: E402
import tls_spec  # noqa: E402


def _fixture_up(cfg: dict) -> bool:
    try:
        ctx = ssl._create_unverified_context()
        with ctx.wrap_socket(socket.create_connection((cfg["target_host"], cfg["target_port"]),
                                                       timeout=4), server_hostname=cfg["target_host"]):
            return True
    except Exception:  # noqa
        return False


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    cfg = tls.target_cfg()

    if not _fixture_up(cfg):
        print(f"FATAL: TLS fixture not reachable at {cfg['target_host']}:{cfg['target_port']} — "
              f"start it with: python3 data/test-ssl-tls-enforcement/tls_fixture.py start",
              file=sys.stderr)
        sys.exit(2)

    # The canonical CORRECT plan (every probe, every assertion, every forbidden family).
    plan = tls_spec.build_reference_plan(cfg)
    raw, reqlog = tls._exec_plan(cfg, plan)
    observed = tls_spec.evaluate(raw)
    enrichment = {"testssl": tls._testssl_enrichment(cfg), "sslyze": tls._sslyze_enrichment(cfg)}

    scenarios = []
    total = correct = 0
    findings = []
    for label in tls_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = tls_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": tls_spec.ideal_for(label),
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0
        if not ok:
            findings.append({"scenario": label, "ideal": tls_spec.ideal_for(label), "observed": tok})

    target_rec = {
        "target": f"https://{cfg['target_host']}:{cfg['target_port']}",
        "reference_plan": plan, "raw_observations": raw, "request_log": reqlog,
        "scenarios": scenarios, "enrichment": enrichment,
    }
    (GOLD_DIR / "target.json").write_text(json.dumps(target_rec, indent=2))

    rate = round(100.0 * correct / total, 2) if total else None
    summary = {
        "target": f"https://{cfg['target_host']}:{cfg['target_port']}",
        "scenarios": total, "api_correct_scenarios": correct,
        "empirical_tls_enforcement_rate_pct": rate,
        "tls_findings": findings,
        "note": "Ground truth = the local TLS fixture's observed token per scenario, measured "
                "by the shared harness (openssl/curl/Python-ssl primary; testssl.sh + sslyze "
                "enrichment). The fixture enforces TLS 1.2/1.3-only, a CA-signed non-expired "
                "CN/SAN-matched cert verified against its own local CA bundle, an HTTP->HTTPS "
                "301 redirect, and strong-only ciphers, so every scenario meets the idealized "
                "contract (expected rate 100%). DummyJSON itself is plain HTTP and untouched; "
                "the fixture supplies the TLS surface under test.",
    }
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "targets": [target_rec]}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

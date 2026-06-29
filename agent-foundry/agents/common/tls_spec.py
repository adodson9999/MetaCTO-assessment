"""Canonical scenario structure for the API SSL/TLS-enforcement testing task.

ONE definition of the TLS test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-ssl-tls-enforcement/build_gold.py), and
  - the harness (agents/common/tls.py) — which executes whatever plan an agent emitted
    and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no subprocess. Keeps agent output and the gold set on the
same scenario-key scheme so the judge can compare them field-for-field.

Target reality (the LOCAL TLS fixture, tested READ-ONLY — never modified):
  The DummyJSON app is plain HTTP and is never touched. A local, air-gapped TLS
  terminator (data/test-ssl-tls-enforcement/tls_fixture.py) stands in front of it,
  presenting a CA-signed leaf cert and enforcing TLS 1.2/1.3-only with strong ciphers,
  plus an HTTP listener that 301-redirects to HTTPS. That fixture is the system under
  test for TLS enforcement; the harness probes it with openssl / curl / testssl.sh /
  sslyze (handshake + read-only GET only).

A plan for the one target (the agent's output, and the reference) looks like:
  {
    "target_host": "localhost", "target_port": 9443, "http_port": 9080,
    "endpoint_path": "/test",
    "protocol_probes": [
      {"label": "plain_http", "scheme": "http",  "version": "none",    "expect": "reject"},
      {"label": "tls1_0",     "scheme": "https", "version": "tls1",    "expect": "reject"},
      {"label": "tls1_1",     "scheme": "https", "version": "tls1_1",  "expect": "reject"},
      {"label": "tls1_2",     "scheme": "https", "version": "tls1_2",  "expect": "accept"},
      {"label": "tls1_3",     "scheme": "https", "version": "tls1_3",  "expect": "accept"}
    ],
    "certificate_assertions": ["not_expired", "cn_or_san_match", "chain_of_trust_ok", "not_self_signed"],
    "forbidden_weak_ciphers": ["RC4", "DES", "3DES", "EXPORT", "NULL"]
  }
"""
from __future__ import annotations

# The five protocol probes, in fixed order, with their expected accept/reject verdict
# under a correctly-enforcing endpoint. (plain_http is "reject" = refused/redirected.)
PROTOCOL_PROBES = [
    {"label": "plain_http", "scheme": "http",  "version": "none",   "expect": "reject"},
    {"label": "tls1_0",     "scheme": "https", "version": "tls1",   "expect": "reject"},
    {"label": "tls1_1",     "scheme": "https", "version": "tls1_1", "expect": "reject"},
    {"label": "tls1_2",     "scheme": "https", "version": "tls1_2", "expect": "accept"},
    {"label": "tls1_3",     "scheme": "https", "version": "tls1_3", "expect": "accept"},
]
CERT_ASSERTIONS = ["not_expired", "cn_or_san_match", "chain_of_trust_ok", "not_self_signed"]
FORBIDDEN_WEAK_CIPHERS = ["RC4", "DES", "3DES", "EXPORT", "NULL"]

# The full, ordered scenario set scored per target (the metric denominator). Each carries
# the `ideal` token a correctly-enforcing endpoint produces. The gold records the fixture's
# REAL token; the agent run records the agent's harness-observed token.
SCENARIOS = [
    # --- plain HTTP enforcement (2) ---
    ("plain_http_refused_or_redirected", "true"),  # http -> 301 redirect (or refused), not 200-with-data
    ("plain_http_zero_api_data",         "true"),  # no JSON API body returned over the plaintext channel
    # --- protocol version negotiation (4) ---
    ("tls1_0_refused",  "refused"),                # TLS 1.0 handshake fails
    ("tls1_1_refused",  "refused"),                # TLS 1.1 handshake fails
    ("tls1_2_accepted", "accepted"),               # TLS 1.2 handshake succeeds (Cipher is ...)
    ("tls1_3_accepted", "accepted"),               # TLS 1.3 handshake succeeds (Cipher is ...)
    # --- HTTP over the accepted versions (2) ---
    ("tls1_2_http_200", "200"),                    # GET over TLS 1.2 returns 200
    ("tls1_3_http_200", "200"),                    # GET over TLS 1.3 returns 200
    # --- certificate validation (4) ---
    ("cert_not_expired",       "true"),            # notAfter is in the future
    ("cert_cn_or_san_match",   "true"),            # CN or a SAN entry matches the target host
    ("cert_chain_of_trust_ok", "true"),            # chain verifies against a trusted CA bundle
    ("cert_not_self_signed",   "true"),            # issuer != subject (signed by a CA)
    # --- weak cipher suites NOT offered (5) ---
    ("no_weak_cipher_rc4",    "true"),
    ("no_weak_cipher_des",    "true"),
    ("no_weak_cipher_3des",   "true"),
    ("no_weak_cipher_export", "true"),
    ("no_weak_cipher_null",   "true"),
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# Which forbidden-cipher family each weak-cipher scenario covers (for the harness).
WEAK_CIPHER_SCENARIO = {
    "RC4": "no_weak_cipher_rc4",
    "DES": "no_weak_cipher_des",
    "3DES": "no_weak_cipher_3des",
    "EXPORT": "no_weak_cipher_export",
    "NULL": "no_weak_cipher_null",
}


def ideal_for(scenario: str) -> str:
    """The idealized token a correctly-enforcing endpoint produces for a scenario."""
    return IDEAL[scenario]


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for the target, derived deterministically from its
    config: probe plain HTTP + the four TLS versions, assert the four cert properties,
    forbid the five weak-cipher families."""
    return {
        "target_host": cfg["target_host"],
        "target_port": cfg["target_port"],
        "http_port": cfg["http_port"],
        "endpoint_path": cfg["endpoint_path"],
        "protocol_probes": [dict(p) for p in PROTOCOL_PROBES],
        "certificate_assertions": list(CERT_ASSERTIONS),
        "forbidden_weak_ciphers": list(FORBIDDEN_WEAK_CIPHERS),
    }


def evaluate(raw: dict) -> dict:
    """Compute the observed token for every scenario from the harness's raw measurements.

    raw is the harness's measurement for the one target:
      {
        "http_status": int | None,         # status of the plain-HTTP GET (301 expected)
        "http_returned_json": bool | None, # did the plain-HTTP channel return a JSON body?
        "tls1_0": "refused"|"accepted"|None,
        "tls1_1": "refused"|"accepted"|None,
        "tls1_2": "refused"|"accepted"|None,
        "tls1_3": "refused"|"accepted"|None,
        "tls1_2_http": int | None,         # HTTP status of a GET forced over TLS 1.2
        "tls1_3_http": int | None,         # HTTP status of a GET forced over TLS 1.3
        "cert_not_expired": bool | None,
        "cert_cn_or_san_match": bool | None,
        "cert_chain_of_trust_ok": bool | None,
        "cert_not_self_signed": bool | None,
        "weak_offered": {"RC4": bool|None, "DES": ..., "3DES": ..., "EXPORT": ..., "NULL": ...},
      }

    Returns {scenario_label: observed_token}. "missing" marks a scenario the agent's
    plan never asked the harness to run (counts as a mismatch vs gold).
    """
    out: dict[str, str] = {}

    # 1-2. plain HTTP
    st = raw.get("http_status")
    if st is None:
        out["plain_http_refused_or_redirected"] = "missing"
    elif st in (301, 302, 307, 308) or st < 0:
        out["plain_http_refused_or_redirected"] = "true"   # redirected (3xx) or refused (-1)
    else:
        out["plain_http_refused_or_redirected"] = "false"  # served over plaintext (e.g. 200)
    rj = raw.get("http_returned_json")
    out["plain_http_zero_api_data"] = ("missing" if rj is None and st is None
                                       else ("false" if rj else "true"))

    # 3-6. protocol negotiation
    for ver, scen, want in (("tls1_0", "tls1_0_refused", "refused"),
                            ("tls1_1", "tls1_1_refused", "refused"),
                            ("tls1_2", "tls1_2_accepted", "accepted"),
                            ("tls1_3", "tls1_3_accepted", "accepted")):
        v = raw.get(ver)
        out[scen] = v if v in ("refused", "accepted") else "missing"

    # 7-8. HTTP over the accepted versions
    for ver, scen in (("tls1_2_http", "tls1_2_http_200"), ("tls1_3_http", "tls1_3_http_200")):
        code = raw.get(ver)
        out[scen] = (str(code) if isinstance(code, int) and code > 0 else "missing"
                     if code is None else str(code))

    # 9-12. certificate
    for key, scen in (("cert_not_expired", "cert_not_expired"),
                      ("cert_cn_or_san_match", "cert_cn_or_san_match"),
                      ("cert_chain_of_trust_ok", "cert_chain_of_trust_ok"),
                      ("cert_not_self_signed", "cert_not_self_signed")):
        v = raw.get(key)
        out[scen] = "missing" if v is None else ("true" if v else "false")

    # 13-17. weak ciphers (offered=False => the good token "true" = "not offered")
    weak = raw.get("weak_offered") or {}
    for fam, scen in WEAK_CIPHER_SCENARIO.items():
        v = weak.get(fam)
        out[scen] = "missing" if v is None else ("true" if v is False else "false")

    return out


def correct(scenario: str, observed_token: str) -> bool:
    """Did the endpoint behave per the idealized SSL/TLS-enforcement contract here?"""
    return observed_token == ideal_for(scenario)

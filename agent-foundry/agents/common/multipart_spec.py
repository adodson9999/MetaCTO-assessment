"""Canonical scenario structure for the API multipart/form-data handling testing task.

ONE definition of the multipart test plan + the per-scenario evaluation, plus the
deterministic file-byte builders, shared by:
  - the deterministic gold reference (data/test-multipart-form-data-handling/build_gold.py), and
  - the harness (agents/common/multipart.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same (endpoint, scenario) key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same key
scheme so the judge can compare them field-for-field. The PNG byte builder is a pure
function of size, so an exactly-N-byte PNG has one deterministic MD5 the gold and
every agent's harness reproduce identically.

Target reality (DummyJSON, tested AS-IS — its repo/data are NEVER modified):
  - DummyJSON DOES parse multipart/form-data: a global multer middleware
    (src/middleware/clean-request.js) parses the parts, enforces a 5 MiB per-file /
    25 MiB total-payload cap, then DELETES the temp files and calls next(). The text
    parts land in req.body, so a create route that echoes a recognized body field
    (POST /products/add echoes title+category; POST /users/add echoes firstName+
    lastName) returns 201 with those text fields preserved EXACTLY.
  - But DummyJSON implements only the PARSING half of the idealized multipart contract.
    It never stores the uploaded file, so the create response carries no document_url
    and the file is not downloadable (no MD5 round-trip); its /add routes are
    non-persistent simulations, so a follow-up GET of the new id is not found; it does
    no required-field validation (a missing text part still returns 201, not 400); it
    returns 415 from no route (a wrong Content-Type application/json body is just the
    normal JSON create, 201); and a single over-limit file trips multer's own parse
    error (HTTP 400), not the documented 413 — only a >25 MiB TOTAL payload returns 413.

  The IDEALIZED multipart contract (declared in
  data/test-multipart-form-data-handling/multipart_openapi.json, authored for the task
  WITHOUT touching DummyJSON) is what each scenario's `ideal` token encodes; the gold
  records the API's REAL observed token. Where they differ is a genuine QA finding about
  DummyJSON, not an agent bug — mirroring how the auth build surfaced the stateless-JWT
  revoke gap and the rate-limit build surfaced the absent limiter.

A plan for one upload endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/products/add",
    "method": "POST",
    "text_fields": [
      {"name": "title",    "value": "Test Entity"},
      {"name": "category", "value": "A"}
    ],
    "file_field": {"name": "document", "media_type": "image/png", "size_bytes": 51200},
    "max_allowed_file_bytes": 5242880,
    "readback_path": "/products/{id}",
    "cases": [
      {"label": "create_status"}, {"label": "text_field_a_exact"},
      {"label": "text_field_b_exact"}, {"label": "document_url_present"},
      {"label": "file_md5_roundtrip"}, {"label": "persisted_readback"},
      {"label": "oversized_rejected"}, {"label": "missing_required_field"},
      {"label": "wrong_content_type"}
    ]
  }
"""
from __future__ import annotations

import hashlib
import struct
import zlib
from functools import lru_cache

# Documented idealized contract constants (the world the agents are briefed from).
SUCCESS_CODE = 201
OVER_SIZE_CODE = 413          # an over-maximum file should be rejected with exactly 413
MISSING_FIELD_CODE = 400      # a missing required text part should be rejected with 400
WRONG_CTYPE_CODE = 415        # a wrong request Content-Type should be rejected with 415

# The nine ordered scenarios scored per endpoint (the metric denominator per endpoint).
# `ideal` is the token a perfectly-conforming multipart API would produce; the gold
# records the REAL token DummyJSON produces.
SCENARIOS = [
    ("create_status",          "201"),
    ("text_field_a_exact",     "exact"),
    ("text_field_b_exact",     "exact"),
    ("document_url_present",   "present"),
    ("file_md5_roundtrip",     "match"),
    ("persisted_readback",     "persisted"),
    ("oversized_rejected",     "413"),
    ("missing_required_field", "400"),
    ("wrong_content_type",     "415"),
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
CASE_LABELS = list(SCENARIO_LABELS)   # the agent emits one case object per label, in order
IDEAL = dict(SCENARIOS)


def ideal_for(scenario: str, _cfg: dict | None = None) -> str:
    """The idealized token for a scenario. cfg is accepted for call-site symmetry."""
    return IDEAL[scenario]


# --------------------------------------------------------------------------- #
# Deterministic file-byte builders (pure; same size -> same bytes -> same MD5)
# --------------------------------------------------------------------------- #
_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _png_chunk(tag: bytes, data: bytes) -> bytes:
    return (struct.pack(">I", len(data)) + tag + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF))


@lru_cache(maxsize=16)
def png_bytes(n: int) -> bytes:
    """A deterministic PNG of EXACTLY n bytes.

    Structure: the 8-byte PNG signature + a 1x1 IHDR chunk + an IDAT chunk whose
    payload is padded so the whole file lands on exactly n bytes + IEND. It carries the
    PNG magic number and a well-formed IHDR, so a server sniffing the magic bytes or the
    declared image/png type accepts it; beyond that its only purpose is to be an
    exactly-n-byte blob with one stable MD5 for the byte-for-byte round-trip check.
    """
    ihdr = _png_chunk(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0))
    iend = _png_chunk(b"IEND", b"")
    fixed_no_idat = len(_PNG_SIG) + len(ihdr) + len(iend)
    idat_overhead = 12  # length(4) + tag(4) + crc(4)
    if n < fixed_no_idat + idat_overhead:
        # Too small for a real IDAT chunk: emit the signature + raw filler to exactly n.
        return (_PNG_SIG + b"\x00" * max(0, n - len(_PNG_SIG)))[:n].ljust(n, b"\x00")
    payload_len = n - fixed_no_idat - idat_overhead
    idat = _png_chunk(b"IDAT", b"\x00" * payload_len)
    out = _PNG_SIG + ihdr + idat + iend
    # Defensive exact-length guarantee against any off-by-one.
    return out[:n].ljust(n, b"\x00") if len(out) != n else out


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# --------------------------------------------------------------------------- #
# Reference plan (the canonical CORRECT plan one perfect agent emits per endpoint)
# --------------------------------------------------------------------------- #
def build_reference_plan(cfg: dict) -> dict:
    a = cfg["text_field_a"]
    b = cfg["text_field_b"]
    return {
        "endpoint": cfg["endpoint"],
        "method": cfg["method"],
        "text_fields": [
            {"name": a["name"], "value": a["value"]},
            {"name": b["name"], "value": b["value"]},
        ],
        "file_field": {
            "name": cfg["file_field"],
            "media_type": cfg["file_media_type"],
            "size_bytes": cfg["file_size_bytes"],
        },
        "max_allowed_file_bytes": cfg["max_allowed_file_bytes"],
        "readback_path": cfg["readback_path"],
        "cases": [{"label": lbl} for lbl in CASE_LABELS],
    }


# --------------------------------------------------------------------------- #
# Evaluation: raw observations -> observed token per scenario
# --------------------------------------------------------------------------- #
def _status_token(code) -> str:
    """None -> 'missing'; otherwise the EXACT status code as a string. The task is about
    exact codes (413 != 400 != 415 != 404), so there is no class-collapsing."""
    if code is None:
        return "missing"
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return "missing"


def evaluate(obs: dict) -> dict:
    """Compute the observed token for every scenario from the harness's raw measurement.

    obs structure (per endpoint):
      {
        "create":   {"ran": bool, "status": int|None,
                     "text_a": "exact"|"mismatch"|"absent", "text_b": ...,
                     "document_url_present": bool},
        "download": {"ran": bool, "md5_match": bool|None, "no_url": bool},
        "readback": {"ran": bool, "persisted": bool},
        "oversized":     {"ran": bool, "status": int|None},
        "missing_field": {"ran": bool, "status": int|None, "msg_refs_field": bool},
        "wrong_ctype":   {"ran": bool, "status": int|None},
      }
    A request the agent never planned -> the dependent scenario scores 'missing'
    (a mismatch vs gold).
    """
    out: dict[str, str] = {}
    create = obs.get("create") or {}
    download = obs.get("download") or {}
    readback = obs.get("readback") or {}
    oversized = obs.get("oversized") or {}
    missing = obs.get("missing_field") or {}
    wrong = obs.get("wrong_ctype") or {}

    cran = bool(create.get("ran"))
    out["create_status"] = _status_token(create.get("status")) if cran else "missing"
    out["text_field_a_exact"] = create.get("text_a", "absent") if cran else "missing"
    out["text_field_b_exact"] = create.get("text_b", "absent") if cran else "missing"
    out["document_url_present"] = ("present" if create.get("document_url_present") else "absent") if cran else "missing"

    if not download.get("ran"):
        out["file_md5_roundtrip"] = "missing"
    elif download.get("no_url"):
        out["file_md5_roundtrip"] = "no_url"
    else:
        out["file_md5_roundtrip"] = "match" if download.get("md5_match") else "mismatch"

    out["persisted_readback"] = (("persisted" if readback.get("persisted") else "not_persisted")
                                 if readback.get("ran") else "missing")

    out["oversized_rejected"] = _status_token(oversized.get("status")) if oversized.get("ran") else "missing"

    if not missing.get("ran"):
        out["missing_required_field"] = "missing"
    else:
        code = missing.get("status")
        out["missing_required_field"] = "400" if (code == 400 and missing.get("msg_refs_field")) else _status_token(code)

    out["wrong_content_type"] = _status_token(wrong.get("status")) if wrong.get("ran") else "missing"
    return out


def correct(scenario: str, observed_token: str, cfg: dict | None = None) -> bool:
    """Did the API behave per the idealized multipart contract for this scenario?"""
    return observed_token == ideal_for(scenario, cfg)

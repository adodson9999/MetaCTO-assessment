"""Canonical scenario structure for the API file-upload-and-download testing task.

ONE definition of the upload/download test plan + the per-scenario evaluation, plus
the deterministic file-byte builders, shared by:
  - the deterministic gold reference (data/test-file-upload-and-download/build_gold.py), and
  - the harness (agents/common/upload.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field. The
file-byte builders are pure functions of (size, mime), so an exactly-N-byte file has
one deterministic MD5 that the gold and every agent's harness reproduce identically.

Target reality (this DummyJSON fork, tested as-is — never modified):
  - The fork DOES handle multipart/form-data uploads via a global middleware
    (src/middleware/clean-request.js + a multer instance, src/helpers/index.js) with a
    documented per-file limit of MAX_FILE_SIZE = 5 MiB (5242880 bytes). A small file
    POSTed to a real resource route (e.g. /products/add) is accepted with that route's
    success code; the route SIMULATES the add (DummyJSON never persists) and returns no
    file "url".
  - Three real divergences from the idealized upload contract are the QA findings this
    task surfaces: (1) accepted uploads return NO downloadable "url", so the byte-for-byte
    MD5 round-trip cannot run at all (File Integrity Rate is untestable -> 0%); (2) the
    size limit is enforced but a single over-limit file returns 400 ("Error processing
    multipart data: File too large", from multer's LIMIT_FILE_SIZE wrapped by the catch)
    rather than the documented 413 — and the boundary is exclusive, so a file of exactly
    MAX_FILE_SIZE is also rejected; the explicit 413 path only fires above the 25 MiB
    total-payload limit (Over-Size Rejection Rate by the 413 definition -> 0%); (3) there
    is no MIME filter, so an application/octet-stream file is accepted, never the
    documented 415 (Invalid MIME Rejection Rate -> 0%).
  - The idealized upload contract (a 1KB and an exactly-MAX_SIZE file accepted with
    success_code + a "url"; a MAX_SIZE+1 file rejected with exactly 413 and no "url"; a
    disallowed-MIME file rejected with exactly 415 and no "url"; each accepted file
    downloadable at its URL with 200, Content-Type image/jpeg, and a byte-for-byte
    -identical MD5) is what each scenario's `ideal` token encodes; the gold records the
    API's REAL token. Where they differ is a genuine QA finding about the fork, not an
    agent bug — mirroring how test-rate-limit-enforcement surfaced the absent limiter.

A plan for one upload endpoint (the agent's output, and the reference) looks like:
  {
    "upload_endpoint": "/products/add",
    "max_size_bytes": 5242880,
    "allowed_mime_types": ["image/jpeg", "image/png"],
    "success_code": 201, "over_size_code": 413,
    "invalid_mime_code": 415, "download_success_code": 200,
    "uploads": [
      {"label": "file_1kb",     "size_bytes": 1024,    "mime_type": "image/jpeg",
       "expect_code": 201, "expect_url": true},
      {"label": "file_max",     "size_bytes": 5242880, "mime_type": "image/jpeg",
       "expect_code": 201, "expect_url": true},
      {"label": "file_over",    "size_bytes": 5242881, "mime_type": "image/jpeg",
       "expect_code": 413, "expect_url": false},
      {"label": "file_invalid", "size_bytes": 1024,    "mime_type": "application/octet-stream",
       "expect_code": 415, "expect_url": false}
    ],
    "downloads": [
      {"label": "download_1kb", "source": "file_1kb",
       "expect_code": 200, "expect_content_type_prefix": "image/jpeg", "expect_md5_match": true},
      {"label": "download_max", "source": "file_max",
       "expect_code": 200, "expect_content_type_prefix": "image/jpeg", "expect_md5_match": true}
    ]
  }
"""
from __future__ import annotations

import hashlib
import struct
from functools import lru_cache

# The documented contract the agents are briefed from. max_size_bytes is grounded in
# the fork's real source constant MAX_FILE_SIZE = 5 * 1024 * 1024 (src/helpers/index.js).
DEFAULT_MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MiB documented maximum upload size
DEFAULT_ALLOWED_MIME_TYPES = ["image/jpeg", "image/png"]
SUCCESS_CODE = 201
OVER_SIZE_CODE = 413
INVALID_MIME_CODE = 415
DOWNLOAD_SUCCESS_CODE = 200

# Fixed sizes/types for the four upload cases.
FILE_1KB_BYTES = 1024
INVALID_FILE_BYTES = 1024                 # the .exe case; its size is irrelevant to the 415 check
VALID_MIME = "image/jpeg"
INVALID_MIME = "application/octet-stream"

# The four upload cases, in order. `size` is resolved against max_size_bytes by
# build_reference_plan (file_max = MAX, file_over = MAX+1); the others are fixed.
UPLOAD_CASES = [
    {"label": "file_1kb",     "size": "fixed_1kb",   "mime": VALID_MIME,   "expect_code": SUCCESS_CODE,      "expect_url": True},
    {"label": "file_max",     "size": "max",         "mime": VALID_MIME,   "expect_code": SUCCESS_CODE,      "expect_url": True},
    {"label": "file_over",    "size": "max_plus_1",  "mime": VALID_MIME,   "expect_code": OVER_SIZE_CODE,    "expect_url": False},
    {"label": "file_invalid", "size": "fixed_1kb",   "mime": INVALID_MIME, "expect_code": INVALID_MIME_CODE, "expect_url": False},
]

# The two downloads (one per successfully-uploadable file), in order.
DOWNLOAD_CASES = [
    {"label": "download_1kb", "source": "file_1kb"},
    {"label": "download_max", "source": "file_max"},
]

# The full, ordered scenario set scored per endpoint (the metric denominator).
# `ideal` is the token a perfectly-conforming API would produce; gold records the
# REAL token DummyJSON produces.
SCENARIOS = [
    ("upload_1kb_status",              "201"),
    ("upload_1kb_url_present",         "true"),
    ("upload_max_status",              "201"),
    ("upload_max_url_present",         "true"),
    ("upload_over_status",             "413"),
    ("upload_over_url_absent",         "true"),
    ("upload_invalid_status",          "415"),
    ("upload_invalid_url_absent",      "true"),
    ("download_1kb_status",            "200"),
    ("download_1kb_content_type_jpeg", "true"),
    ("download_1kb_md5_match",         "true"),
    ("download_max_status",            "200"),
    ("download_max_content_type_jpeg", "true"),
    ("download_max_md5_match",         "true"),
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)


# Status scenarios resolve their idealized code from the endpoint's documented contract
# (so an endpoint whose documented success_code is 200 vs 201 is judged against its own
# contract, not a hard-coded 201). Boolean scenarios stay constant.
_STATUS_IDEAL_FIELD = {
    "upload_1kb_status": "success_code",
    "upload_max_status": "success_code",
    "upload_over_status": "over_size_code",
    "upload_invalid_status": "invalid_mime_code",
    "download_1kb_status": "download_success_code",
    "download_max_status": "download_success_code",
}


def ideal_for(scenario: str, cfg: dict | None = None) -> str:
    """The idealized token for a scenario. Status scenarios resolve their code from cfg's
    documented contract when cfg is provided (falling back to the constant in IDEAL);
    boolean scenarios are constant."""
    if scenario in _STATUS_IDEAL_FIELD and cfg:
        return str(cfg.get(_STATUS_IDEAL_FIELD[scenario], IDEAL[scenario]))
    return IDEAL[scenario]


# --------------------------------------------------------------------------- #
# Deterministic file-byte builders (pure; same bytes -> same MD5 everywhere)
# --------------------------------------------------------------------------- #
_SOI = b"\xFF\xD8"
# Minimal JFIF APP0 segment: marker FFE0 + length 0x0010 + 14-byte JFIF payload = 18 bytes.
_APP0 = b"\xFF\xE0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
_EOI = b"\xFF\xD9"
_COM_MAX_PAYLOAD = 65533                  # so the 2-byte length (payload + 2) <= 65535


@lru_cache(maxsize=64)
def jpeg_bytes(n: int) -> bytes:
    """A deterministic JPEG of EXACTLY n bytes.

    Structure: SOI + JFIF APP0 + zero or more COM (comment) segments padding to the
    exact length + EOI. It carries the JPEG magic number and a valid JFIF header and
    is built from well-formed marker segments, so a server sniffing the magic bytes or
    the declared image/jpeg type accepts it; its only purpose beyond that is to be an
    exactly-n-byte blob with one stable MD5 for the byte-for-byte round-trip check.
    """
    if n < len(_SOI):
        return b"\x00" * n
    fixed = len(_SOI) + len(_APP0) + len(_EOI)            # 22
    if n <= fixed:
        # Too small for a COM segment; keep the magic + EOI and land exactly n bytes.
        head = (_SOI + _APP0)[:max(0, n - len(_EOI))]
        return (head + _EOI)[:n].ljust(n, b"\x00")
    out = bytearray(_SOI + _APP0)
    pad = n - fixed                                       # bytes to place as COM segments
    while pad > 0:
        if pad < 4:                                       # can't form a COM header; raw filler
            out += b"\x00" * pad
            pad = 0
            break
        payload = min(_COM_MAX_PAYLOAD, pad - 4)
        out += b"\xFF\xFE" + struct.pack(">H", payload + 2) + b"\x00" * payload
        pad -= 4 + payload
    out += _EOI
    return bytes(out)


@lru_cache(maxsize=64)
def exe_bytes(n: int) -> bytes:
    """A deterministic Windows-PE-flavoured blob of EXACTLY n bytes: the "MZ" magic
    number + zero filler. Used as the invalid-MIME upload (application/octet-stream)."""
    if n < 2:
        return b"\x00" * n
    return (b"MZ" + b"\x00" * (n - 2))


def file_bytes(mime_type: str, size_bytes: int) -> bytes:
    """The deterministic body for an upload case: a JPEG for image/* sizes, an MZ blob
    otherwise. Exactly size_bytes long with a stable MD5."""
    if str(mime_type).startswith("image/"):
        return jpeg_bytes(size_bytes)
    return exe_bytes(size_bytes)


def md5_hex(data: bytes) -> str:
    return hashlib.md5(data).hexdigest()


# --------------------------------------------------------------------------- #
# Reference plan
# --------------------------------------------------------------------------- #
def _resolved_size(size_token: str, max_size: int) -> int:
    if size_token == "fixed_1kb":
        return FILE_1KB_BYTES
    if size_token == "max":
        return max_size
    if size_token == "max_plus_1":
        return max_size + 1
    raise ValueError(f"unknown size token: {size_token}")


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one upload endpoint, derived deterministically
    from its config: the four upload cases (1KB, exactly MAX, MAX+1, invalid-MIME) and
    the two downloads (one per accepted file)."""
    max_size = cfg["max_size_bytes"]
    uploads = []
    for c in UPLOAD_CASES:
        uploads.append({
            "label": c["label"],
            "size_bytes": _resolved_size(c["size"], max_size),
            "mime_type": c["mime"],
            "expect_code": c["expect_code"],
            "expect_url": c["expect_url"],
        })
    downloads = []
    for d in DOWNLOAD_CASES:
        downloads.append({
            "label": d["label"],
            "source": d["source"],
            "expect_code": DOWNLOAD_SUCCESS_CODE,
            "expect_content_type_prefix": VALID_MIME,
            "expect_md5_match": True,
        })
    return {
        "upload_endpoint": cfg["upload_endpoint"],
        "max_size_bytes": max_size,
        "allowed_mime_types": cfg.get("allowed_mime_types", DEFAULT_ALLOWED_MIME_TYPES),
        "success_code": cfg.get("success_code", SUCCESS_CODE),
        "over_size_code": cfg.get("over_size_code", OVER_SIZE_CODE),
        "invalid_mime_code": cfg.get("invalid_mime_code", INVALID_MIME_CODE),
        "download_success_code": cfg.get("download_success_code", DOWNLOAD_SUCCESS_CODE),
        "uploads": uploads,
        "downloads": downloads,
    }


# --------------------------------------------------------------------------- #
# Evaluation
# --------------------------------------------------------------------------- #
def _status_token(code) -> str:
    """None -> 'none', otherwise the exact status code as a string. The whole point of
    the task is exact codes (413 != 404, 415 != 400), so no class-collapsing."""
    if code is None:
        return "none"
    try:
        return str(int(code))
    except (TypeError, ValueError):
        return "none"


def _bool_token(value) -> str:
    return "true" if value else "false"


def evaluate(obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    obs is the harness's raw measurement for one endpoint:
      {
        "uploads": {
          "file_1kb":     {"ran": bool, "status": int|None, "url_in_body": bool|None},
          "file_max":     {...}, "file_over": {...}, "file_invalid": {...}
        },
        "downloads": {
          "download_1kb": {"ran": bool, "status": int|None,
                           "content_type": str|None, "md5_match": bool|None},
          "download_max": {...}
        }
      }

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    uploads = obs.get("uploads") or {}
    downloads = obs.get("downloads") or {}
    out: dict[str, str] = {}

    def up(label: str):
        u = uploads.get(label) or {}
        return bool(u.get("ran")), u

    def status_scn(label, u_label):
        ran, u = up(u_label)
        return _status_token(u.get("status")) if ran else "missing"

    def url_present_scn(u_label):
        ran, u = up(u_label)
        return _bool_token(u.get("url_in_body")) if ran else "missing"

    def url_absent_scn(u_label):
        ran, u = up(u_label)
        return _bool_token(not u.get("url_in_body")) if ran else "missing"

    out["upload_1kb_status"] = status_scn("upload_1kb_status", "file_1kb")
    out["upload_1kb_url_present"] = url_present_scn("file_1kb")
    out["upload_max_status"] = status_scn("upload_max_status", "file_max")
    out["upload_max_url_present"] = url_present_scn("file_max")
    out["upload_over_status"] = status_scn("upload_over_status", "file_over")
    out["upload_over_url_absent"] = url_absent_scn("file_over")
    out["upload_invalid_status"] = status_scn("upload_invalid_status", "file_invalid")
    out["upload_invalid_url_absent"] = url_absent_scn("file_invalid")

    def dl(label: str):
        d = downloads.get(label) or {}
        return bool(d.get("ran")), d

    def dl_status(label):
        ran, d = dl(label)
        return _status_token(d.get("status")) if ran else "missing"

    def dl_ct(label):
        ran, d = dl(label)
        if not ran:
            return "missing"
        ct = (d.get("content_type") or "")
        return _bool_token(str(ct).startswith(VALID_MIME))

    def dl_md5(label):
        ran, d = dl(label)
        return _bool_token(d.get("md5_match")) if ran else "missing"

    out["download_1kb_status"] = dl_status("download_1kb")
    out["download_1kb_content_type_jpeg"] = dl_ct("download_1kb")
    out["download_1kb_md5_match"] = dl_md5("download_1kb")
    out["download_max_status"] = dl_status("download_max")
    out["download_max_content_type_jpeg"] = dl_ct("download_max")
    out["download_max_md5_match"] = dl_md5("download_max")

    return out


def correct(scenario: str, observed_token: str, cfg: dict | None = None) -> bool:
    """Did the API behave per the idealized upload/download contract for this scenario?"""
    return observed_token == ideal_for(scenario, cfg)

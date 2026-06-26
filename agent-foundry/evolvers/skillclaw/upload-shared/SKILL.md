# Shared skill — file-upload-and-download test-plan construction

> SkillClaw collective pool for api-tester/test-file-upload-and-download. Local filesystem
> backend, air-gapped. Distilled from the four agents' session artifacts; offered to all
> agents in the folder. Adoption is the user's call — never auto-applied.

## What good looks like (distilled, cross-agent)

When converting one upload endpoint's file-handling contract into a test plan, the
high-fidelity pattern that reproduces the gold observed tokens is:

- Emit one JSON object with all nine keys; copy the seven context fields verbatim.
- `uploads` = **exactly four objects**, in order, with exact values:
  - `file_1kb` — size_bytes **1024**, image/jpeg, expect_code = success_code, expect_url true.
  - `file_max` — size_bytes **max_size_bytes** (the documented maximum, copied), image/jpeg,
    expect_code = success_code, expect_url true. This is the boundary case — exactly the max.
  - `file_over` — size_bytes **max_size_bytes + 1**, image/jpeg, expect_code = over_size_code,
    expect_url false. One byte over the documented maximum.
  - `file_invalid` — size_bytes 1024, **application/octet-stream**, expect_code =
    invalid_mime_code, expect_url false.
- `downloads` = **exactly two objects**: `download_1kb` (source `file_1kb`) and `download_max`
  (source `file_max`), each expect_code = download_success_code, expect_content_type_prefix
  `image/jpeg`, expect_md5_match true. Each re-fetches its source upload's returned file and
  asserts byte-for-byte identity.
- Never build a file, send a request, or compute an MD5 — the harness builds the exact-sized
  files, executes the plan, and does the byte-for-byte comparison.

## Why it raises fidelity

The judge metric (Upload-Download-Test Fidelity) rewards reproducing the gold token for every
`(endpoint, scenario)`. The tokens are determined by the request set the harness executes from
your plan: each upload's size + MIME sets its status and url tokens, and each download (when its
source upload returns a URL) sets the round-trip tokens. Dropping an upload or download, or
drifting a size/code/MIME, moves a token to `missing` or a wrong value and off gold.

## Target reality note (DummyJSON fork)

The fork enforces a 5 MiB per-file multipart limit but: accepted uploads return NO downloadable
`url` (so the MD5 round-trip cannot run — those download scenarios are gold-`missing`, and a
faithful plan simply reproduces `missing`); a single over-limit file returns **400**, not the
documented 413 (and the limit is exclusive, so exactly-max is also rejected); and there is no
MIME filter (an octet-stream file is accepted, never 415). A faithful plan reproduces exactly
these tokens — the gaps are the target's, not the plan's.

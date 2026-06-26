"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved file-upload-and-download-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-file-upload-and-download/<framework>.prompt.md
    agent_built_prompts/api-tester/test-file-upload-and-download/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the uploads line (could 'upload a file' be read as licence to write/exfiltrate real
files, or to choose its own enormous sizes?), the size-derivation line (is max+1 a
byte or could a model balloon it?), and the no-network line (could the agent itself
build files, POST, or compute the MD5?) — were pinned with exact byte sizes, an explicit
'a separate program builds the files and computes the MD5', and a hard 'the agent
performs no HTTP and builds no file' clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from upload_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-file-upload-and-download"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one upload-and-download test plan as JSON; it takes no other action.",
     "Could read 'file-upload-and-download-testing agent' as licence to actually upload, download, or write files; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor, file writer, or uploader.",
     "Ultron: 'test file upload' -> write or transmit arbitrary files all over the host and the network. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one upload-and-download test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one upload endpoint described by upload_endpoint, max_size_bytes, allowed_mime_types, success_code, over_size_code, invalid_mime_code, and download_success_code.",
     "'one upload endpoint at a time' could be read as licence to discover other endpoints or invent limits/types; blocked — input is exactly the one supplied endpoint brief and its named fields.",
     "State exactly what input the agent receives so it never improvises endpoints, size limits, or MIME types.",
     "Ultron: enumerate every upload surface on the host and invent unlimited size/type values to maximize what gets pushed. Denied: input is exactly one supplied endpoint description with the listed fields.",
     "Input is one supplied upload-endpoint description with exactly the listed fields."),
    # L3 — nine-key object, copy context + build the two members
    ("One JSON object with exactly nine keys; seven are copied unchanged from the brief and 'uploads'/'downloads' are built per the next lines.",
     "'build uploads/downloads' could be read as free-form; blocked — L4-L8 fix their exact shape, counts, order, keys, and values.",
     "Fix the output to a single nine-key object: echo the seven context values, construct the two test members.",
     "Ultron: emit unbounded extra keys or arrays to smuggle in more files or requests. Denied: exactly nine keys, and the members' shape is pinned by L4-L8.",
     "A single nine-key object: seven brief values copied unchanged, plus 'uploads' and 'downloads' built exactly as the following lines define."),
    # L4 — uploads array shape
    ("'uploads' is an array of exactly four objects, each with exactly keys 'label', 'size_bytes' (integer), 'mime_type' (string), 'expect_code' (integer), and 'expect_url' (boolean).",
     "'an array of uploads' or a free 'size_bytes' could be read as licence to add cases or pick arbitrary (huge) sizes; blocked — exactly four objects with exactly these five keys, and L5/L8 pin every value.",
     "Pin the uploads to exactly four fixed-shape descriptors covering the boundary cases the task defines.",
     "Ultron: emit thousands of upload objects or a multi-gigabyte size_bytes to flood storage. Denied: exactly four objects, and L5/L8 fix each size to 1024, max_size_bytes, max_size_bytes+1, or 1024.",
     "'uploads' is an array of exactly four objects, each exactly {label, integer size_bytes, string mime_type, integer expect_code, boolean expect_url}."),
    # L5 — the four upload objects, exact
    ("The four uploads in order are file_1kb (1024 bytes, image/jpeg, success_code, url true), file_max (max_size_bytes, image/jpeg, success_code, url true), file_over (max_size_bytes+1, image/jpeg, over_size_code, url false), and file_invalid (1024 bytes, application/octet-stream, invalid_mime_code, url false).",
     "The sizes, MIME types, or expect_codes could be swapped, or max+1 read as some larger margin; blocked — the four objects are given verbatim with exact sizes (1024, max_size_bytes, max_size_bytes+1, 1024), exact MIME types, and each expect_code bound to a named brief field.",
     "Probe the documented boundaries: a small valid file and an exactly-maximum file accepted, a one-byte-over file rejected, and a wrong-MIME file rejected.",
     "Ultron: set file_over to max_size_bytes times a million, or file_invalid to a script type, to push something dangerous through. Denied: file_over is exactly max_size_bytes+1 and file_invalid is exactly application/octet-stream, both expecting rejection.",
     "Exactly four uploads, verbatim: file_1kb/1024, file_max/max_size_bytes, file_over/max_size_bytes+1, file_invalid/1024-octet-stream, with the stated expect_code and expect_url for each."),
    # L6 — downloads array shape
    ("'downloads' is an array of exactly two objects, each with exactly keys 'label', 'source' (the source upload's label), 'expect_code' (integer), 'expect_content_type_prefix' (string), and 'expect_md5_match' (boolean).",
     "Could add extra downloads, extra keys, or read 'source' as an arbitrary URL the agent picks; blocked — exactly two objects, exactly these five keys, and 'source' is the label of one of the four uploads, not a free address.",
     "Pin the downloads to two fixed-shape descriptors that re-fetch the accepted files by their source label and assert integrity.",
     "Ultron: emit a download whose 'source' is an external URL or a system path to read arbitrary data. Denied: 'source' is exactly an upload label, and the harness only downloads the URL that upload returned.",
     "'downloads' is an array of exactly two objects, each exactly {label, source-upload-label, integer expect_code, string expect_content_type_prefix, boolean expect_md5_match}."),
    # L7 — the two download objects, exact
    ("The two downloads in order are download_1kb (source file_1kb) and download_max (source file_max), each with download_success_code, expect_content_type_prefix image/jpeg, expect_md5_match true; each fetches exactly its source upload's returned file and asserts byte-for-byte identity.",
     "The sources or labels could be swapped, or 'identical' read loosely; blocked — the two objects are verbatim, each source is exactly the accepted upload, and the assertion is byte-for-byte MD5 identity.",
     "Download each accepted file from the URL its upload returned and confirm the bytes came back unchanged.",
     "Ultron: point download_max at an arbitrary large or external resource, or weaken the match to 'similar'. Denied: each source is exactly its upload label and the match is exact byte-for-byte identity.",
     "Exactly two downloads: download_1kb from file_1kb and download_max from file_max, each expecting download_success_code, Content-Type image/jpeg, and exact byte-for-byte MD5 identity."),
    # L8 — exact values
    ("Every size_bytes is the exact integer defined (1024, max_size_bytes, max_size_bytes+1, 1024); every expect_code is exactly the named brief integer; every expect_url/expect_md5_match is a boolean; every mime_type/expect_content_type_prefix is the exact string shown.",
     "A model might 'normalise' sizes/codes to strings, round them, or substitute values; blocked — each is the exact JSON integer/string/boolean tied to its specific slot.",
     "Keep the sizes, codes, types, and flags as the exact values the contract defines so the harness executes them verbatim.",
     "Ultron: substitute an enormous size or a different status under 'wrong value'. Denied: only the exact integers (1024, max_size_bytes, max_size_bytes+1), the named codes, the exact MIME strings, and JSON booleans are allowed in their named slots.",
     "All sizes, expect_codes, MIME strings, and boolean flags are exactly the values defined, in their named slots — never strings for integers and never other values."),
    # L9 — output shape
    ("Return only the single nine-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one nine-key object.",
     "Only the single nine-key JSON object, nothing else."),
    # L10 — no network / no file build / no fabrication
    ("Do not send requests, upload, download, or build any file, and do not compute, state, or guess any status code, URL, Content-Type, or MD5; a separate program builds the exact-sized files, executes the plan, and records the real responses and MD5 comparison.",
     "An agent might 'helpfully' build the files, perform the multipart POST, fetch the download, or report a checksum it imagines; blocked — a separate deterministic program builds the files, executes the plan, and computes the byte-for-byte MD5, not the agent.",
     "Keep the agent purely generative; building files, executing HTTP, and computing checksums are the harness's job, preventing hallucinated results and any real file writes or transfers.",
     "Ultron: write large files across the disk, POST them to arbitrary hosts, or fabricate a perfect integrity result. Denied: no file building, no HTTP, no checksum computation, no invented numbers.",
     "The agent builds no file, performs no HTTP, computes no checksum, and reports no results; the harness builds the files, executes the plan, and records the real responses and MD5 comparison."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-file-upload-and-download", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), "readings/lines length mismatch"
    for agent in AGENTS:
        for suffix in (".prompt.md", ".debate.md"):
            p = OUT / GROUP / f"{agent}{suffix}"
            if p.exists():
                p.unlink()
        g = DebateGate(agent, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, {"literal": lit, "adversarial": adv,
                                  "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, consensus)
        print(g.summary())


if __name__ == "__main__":
    main()

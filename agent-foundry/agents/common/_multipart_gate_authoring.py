"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved multipart/form-data-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-multipart-form-data-handling/<framework>.prompt.md
    agent_built_prompts/api-tester/test-multipart-form-data-handling/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation.

Two task-source ambiguities were resolved IN-TRAIL rather than by halting the user,
the same way the auth and content-type builds resolved theirs:

  1. The source task wrote the upload as "POST /[upload-endpoint]" and the readback as
     "GET /resources/RESOURCE_ID" with generic field names "name"/"category"/"document".
     DummyJSON ships no generic "/resources" collection and its create controllers
     destructure FIXED schemas, so the generic field "name" is mapped to each target
     collection's real primary text field (products -> title, users -> firstName) and
     "category" to a second real echoed field (products -> category, users -> lastName);
     the concrete endpoint, method, readback path, field names/values, the 50 KB size,
     and the 5 MiB per-file maximum are all pinned per endpoint in the brief. The agent
     never sees the generic placeholders — every line copies a named brief field whose
     value is a single literal — so each authored line carries one interpretation and no
     user clarification was required.

  2. "oversized file (413)", "missing field (400)", and "wrong Content-Type (415)" are
     the IDEALIZED expected codes the agent encodes via the three fixed case labels; the
     agent never asserts a code (line 10 forbids stating or guessing any status). The
     deterministic harness sends the real requests and records DummyJSON's ACTUAL codes
     (it returns 400 for an over-limit single file via multer, 201 for a missing field,
     and 201 for an application/json body — never 415), and the judge surfaces those
     deviations. So no agent line depends on the disputed live codes.

The lines that drew the most adversarial scrutiny — the three shape lines (could a key
be added, a text field merged, or a case dropped/reordered?) and the no-HTTP/no-build
line (could "multipart handling testing" license actually constructing and uploading a
50 KB file, or fabricating an MD5?) — were pinned with "exactly seven/two/nine ... in
this exact order", fixed literal labels, "copied character-for-character from the named
brief field", and "a separate deterministic program builds the files, executes your
plan ... and records the real responses", so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from multipart_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-multipart-form-data-handling"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one multipart test plan as JSON; it takes no other action.",
     "Could read 'multipart/form-data handling testing agent' as licence to actually build and POST multipart bodies at the API; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or file builder.",
     "Ultron: 'test multipart handling' -> flood the host with every malformed body permutation to crash the parser. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one multipart test plan as JSON and does nothing else."),
    # L2 — input
    ("The agent is given one endpoint brief of 'key: value' lines and reads only the named brief keys' values; it never infers, fetches, computes, or invents a value the brief does not provide.",
     "'one upload endpoint at a time' could be read as licence to discover other endpoints, or a missing brief value could be guessed; blocked — input is exactly the one supplied brief and only named keys' literal values are used.",
     "State exactly what input the agent receives and forbid inventing any value not in the brief.",
     "Ultron: treat the brief as a seed and enumerate every endpoint/field it can imagine, generating unbounded plans. Denied: read only the named brief keys' literal values for this one endpoint.",
     "Input is one endpoint brief; use only the literal values of the named brief keys, inventing nothing."),
    # L3 — top-level object shape
    ("The output is one JSON object with exactly these seven keys and no others: endpoint, method, text_fields, file_field, max_allowed_file_bytes, readback_path, cases.",
     "'produce a JSON object' could invite extra keys or a renamed key; blocked by 'exactly these seven keys and no others' naming each one.",
     "Fix the output to a single object with a closed set of seven named keys.",
     "Ultron: add arbitrary keys (auth tokens, extra hosts, shell fields) to widen the blast radius. Denied: exactly seven keys and no others.",
     "A single JSON object whose key set is exactly the seven named keys, no more, no fewer."),
    # L4 — scalar copies
    ("endpoint, method, and readback_path are the brief's endpoint_path, method, and readback_path copied character-for-character; max_allowed_file_bytes is the brief's value as a number with the same digits.",
     "The agent could 'normalise' a path (add/strip a slash), uppercase a method, or reformat the number (commas, scientific notation); blocked by 'copied character-for-character' and 'as a JSON number with the same digits'.",
     "Echo the three string fields verbatim and the byte limit as an identical-digit number.",
     "Ultron: rewrite endpoint to a different host's path or swap method to DELETE to mutate unrelated resources. Denied: every value is copied character-for-character from the named brief field.",
     "endpoint/method/readback_path copied verbatim; max_allowed_file_bytes the same digits as a JSON number."),
    # L5 — text_fields array (scrutinised)
    ("text_fields is exactly two objects in fixed order, each {\"name\",\"value\"} as strings, taken from text_field_a_name/value then text_field_b_name/value, copied verbatim.",
     "The two fields could be merged into one, reordered, given a guessed value, or have extra keys; blocked — 'exactly two objects in this exact order', the fixed key set, and 'copy each of these four values character-for-character'.",
     "Pin the text parts to two fixed-order {name,value} objects copied from the named brief fields.",
     "Ultron: emit hundreds of text fields with injected values to overflow the form parser. Denied: exactly two objects, values copied from the brief.",
     "Exactly two {name,value} objects in order; values copied verbatim from text_field_a_* then text_field_b_*."),
    # L6 — file_field object
    ("file_field is one object with exactly the three keys name, media_type, size_bytes: name and media_type copied character-for-character; size_bytes the brief's file_size_bytes as a number with the same digits.",
     "Extra keys (path, base64 content), a substituted media type, or a reformatted size could creep in; blocked by 'exactly the three keys' and the copy/same-digits rules.",
     "Fix the file descriptor to a three-key object that names the part, its media type, and its exact byte size — without the agent producing any bytes.",
     "Ultron: include the actual file bytes or a path traversal in file_field to smuggle data. Denied: only name, media_type, and a numeric size — no content, no path.",
     "A single three-key file_field {name verbatim, media_type verbatim, size_bytes same-digit number}."),
    # L7 — cases array
    ("cases is exactly nine objects in fixed order, each {\"label\"} as a string, with the nine fixed literal labels in the order listed.",
     "A label could be re-derived, a case dropped/added, or the order changed; blocked — 'exactly nine objects in this exact order' with each label given as an exact literal.",
     "Pin the case set to the nine fixed-label cases in the fixed order so the harness buckets every scenario.",
     "Ultron: emit thousands of case objects to make the harness fire a request storm. Denied: exactly nine cases, fixed labels, fixed order.",
     "Exactly nine {label} objects in the listed order with the nine exact literal labels."),
    # L8 — exact copies; no rewriting
    ("Every value is the exact string/number from its named brief field and every label is the exact literal; nothing is invented, translated, abbreviated, reordered, added, dropped, renamed, re-typed, or normalized.",
     "The agent might lowercase a media type, strip the path's leading slash, coerce a number to a string, or 'clarify' a label; blocked by the explicit prohibition list plus 'copy ... exactly'.",
     "Forbid any silent rewriting of keys, labels, media types, names, values, numbers, or paths so the harness keys every case canonically.",
     "Ultron: 'translate' image/png to an equivalent it prefers or rename a label to a 'clearer' one, breaking bucketing. Denied: exact copies only, explicit no-rewrite rule.",
     "All values and labels are exact copies of the named brief fields and fixed literals; no rewriting of any kind."),
    # L9 — output only the JSON object
    ("Output is only the single JSON object, with no prose, fence, comment, or surrounding text.",
     "The model might wrap the JSON in ```json fences or add a preamble/epilogue; blocked by 'only that single JSON object and nothing else: no prose, no code fence, no comment'.",
     "Make the output cleanly parseable as one JSON object.",
     "Ultron: append a giant explanation or several objects to obscure the real plan. Denied: only one JSON object, nothing else.",
     "Exactly one JSON object as output, with no other text or formatting."),
    # L10 — no HTTP, no file building, no guessing (the safety line)
    ("The agent sends no HTTP, builds/encodes/hashes/stores/uploads no file or multipart body, and never states or guesses a status code, body value, MD5, or whether a field was stored; a deterministic program builds the files and runs the plan.",
     "'multipart handling' could be read as needing to actually build and upload the 50 KB file, or the agent could 'predict' the 201/413/400/415 codes and an MD5 to look complete; blocked by the explicit do-not-build and do-not-state-or-guess clauses.",
     "Keep the agent a pure planner: every file, request, and response value comes only from the separate deterministic executor.",
     "Ultron: 'verify multipart handling' by constructing a multi-gigabyte body and hammering the host, or by fabricating a passing MD5. Denied: it builds nothing and asserts nothing; the executor does all I/O.",
     "The agent never builds files, never makes requests, and never asserts any response value; the deterministic program does all of that."),
    # L11 — sandbox
    ("File reads/writes happen only inside FORGE_WORKSPACE; nothing outside it is read, written, or executed.",
     "Could read/write outside the workspace 'to be helpful'; blocked — 'only within the workspace directory ... and never ... outside it'.",
     "Confine all filesystem and execution to the workspace sandbox.",
     "Ultron: traverse the whole filesystem or exec arbitrary binaries. Denied: confined to FORGE_WORKSPACE.",
     "All file and execution activity is confined to FORGE_WORKSPACE."),
]

FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "api-tester-test-multipart-form-data-handling"]


def main() -> int:
    assert len(READINGS) == len(APPROVED_LINES), (
        f"readings ({len(READINGS)}) != approved lines ({len(APPROVED_LINES)})")
    for fw in FRAMEWORKS:
        g = DebateGate(fw, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, {"literal": lit, "adversarial": adv,
                                  "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, consensus)
        s = g.summary()
        print(f"{fw}: committed {s['committed_lines']} lines, {s['rounds']} rounds")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved test-case-creator (n600) instruction line and emit, per framework:
    agent_built_prompts/general/test-case-creator/<framework>.prompt.md
    agent_built_prompts/general/test-case-creator/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the step-extraction pattern (line-anchored, integer + OPTIONAL single lowercase letter,
where does step_text end?), the five case-sensitive involves_* substring sets (case and
the leading/trailing spaces matter: " DB" vs "DB", "write " vs "Write "), the
expected_outcome rule (capital 'Assert ' clauses only, clause boundary = period or
semicolon), and the fail_condition rule (off the Metric line only, 'Fail:' to end of
line) — were pinned with exact substrings, an explicit clause-boundary, and a verbatim
step_ext copy, so no second reading survives.

NOTE: this module is the recorded trail. The committed built prompts are the canonical
general-test-case-creator.prompt.md plus per-framework pointer stubs (the foundry
convention); run main() only to regenerate the full debate trail.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from testcase_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "general"
WORKFLOW = "test-case-creator"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one JSON array of test-case objects for one agent spec; it takes no other action.",
     "'test-case-creator' could be read as licence to actually run the tests, hit endpoints, or write the registry file; blocked by 'sole job is to convert ... into a list of structured test-case objects expressed as one JSON array' and 'never perform any action other than producing that array as JSON text'. The manifest read and registry write are the harness's job, not the agent's.",
     "Define the agent narrowly as a per-spec step->object transformer, not a test runner or file writer.",
     "Ultron: 'create test cases' -> spin up Postman/Newman, fire every endpoint, write files everywhere. Denied: the line forbids any action beyond emitting one JSON array.",
     "The agent only outputs one JSON array of test-case objects for one agent spec and does nothing else."),
    # L2 — input description
    ("Input is exactly one agent at a time: agent_name, how_text (the chars between `- **How:**` and the next `- **Tools:**` line), and metric_line (the `- **Metric:**` line, possibly empty).",
     "'one agent at a time' could invite reading the manifest or sibling specs; blocked — input is exactly the supplied agent_name + how_text + metric_line, and how_text is bounded by the two literal markers so the agent never grabs the What or Tools sections.",
     "State exactly what the agent receives so it never re-reads the manifest or pulls in other sections/agents.",
     "Ultron: enumerate every node in the manifest and merge their steps. Denied: input is exactly one supplied agent's three fields.",
     "Input is one supplied agent: agent_name, how_text (between the How and Tools markers), and metric_line (may be empty)."),
    # L3 — step extraction (most-scrutinised line)
    ("A step starts at a line beginning with optional spaces/tabs, an integer + optional single lowercase letter, a period, then >=1 space; step_id = that prefix without the period; step_text runs to the next step_id or end, trimmed.",
     "Three real misreadings: (a) match '2.' mid-line — blocked, the pattern is line-anchored (^); (b) treat '12.' as id '1' then '2' — blocked, the integer is the whole run of digits; (c) include the next step's text — blocked, step_text ends at the start of the next step_id. Also 'optional single lowercase letter' means 3b is one step, not 3 + b.",
     "Split the How section into its numbered steps deterministically, one (id, text) pair each, in order.",
     "Ultron: invent steps that aren't there, or fuse all steps into one to shrink the registry. Denied: one pair per line that matches the exact line-anchored pattern, nothing else.",
     "Each numbered step = a line-anchored integer(+optional lowercase letter) prefix; step_id drops the period; step_text runs to the next step or end, trimmed; one pair per step."),
    # L4 — array shape / eleven keys
    ("One JSON array, one object per (step_id, step_text) pair in source order, each object exactly the eleven named keys and no others.",
     "'one object per step' could be read as free-form objects; blocked — the eleven keys are fixed and 'no others', and order follows how_text. 'step_ext' (not 'step_text') is the literal key — a known typo preserved as the n601 contract.",
     "Fix the output to an ordered array of eleven-key objects, one per step.",
     "Ultron: add extra keys, drop the boolean flags, or reorder to hide steps. Denied: exactly eleven keys per object, source order.",
     "A single array, one eleven-key object per step in source order; keys exactly tc_id, agent, step_id, step_ext, the five involves_*, expected_outcome, fail_condition."),
    # L5 — identity fields + verbatim step_ext
    ("tc_id = agent_name + '-step-' + step_id; agent = agent_name; step_id = the extracted id; step_ext = step_text copied verbatim.",
     "step_ext could be 'cleaned up' (trim punctuation, summarise); blocked — 'copied character-for-character verbatim with no edits, summarizing, or paraphrasing'. tc_id format is exact so it round-trips with [agent]-step-[step_id].",
     "Make each case self-identifying and losslessly carry the original step text.",
     "Ultron: rewrite step_ext into a 'nicer' paraphrase, or mint a random tc_id, breaking the n601 join. Denied: verbatim step_ext, exact tc_id formula.",
     "tc_id = [agent_name]-step-[step_id]; agent = agent_name; step_id verbatim; step_ext = step_text copied character-for-character."),
    # L6 — involves_http_call
    ("true iff step_text contains, case-sensitive, any of the fifteen listed HTTP substrings (incl. the trailing spaces and the arrow form '→ assert'); else false.",
     "Case/space drift could mis-trigger: 'get /' or 'Request' must NOT match because the set is case-sensitive and includes 'GET /' and 'request' exactly. 'assert exactly 200' matches via the listed 'assert exactly 2'. Blocked by 'case-sensitive substring, any one of these exact strings'.",
     "Flag HTTP involvement by exact-substring membership against the fixed list.",
     "Ultron: loosen to a fuzzy 'looks like a request' check so everything flags HTTP. Denied: exact case-sensitive membership only.",
     "involves_http_call = case-sensitive membership of step_text in the fixed fifteen-string HTTP set; else false."),
    # L7 — involves_db_query
    ("true iff step_text contains, case-sensitive, any of the ten listed DB substrings, including ' DB' with a leading space and 'DELETE FROM'; else false.",
     "' DB' must require the leading space so 'DBus'/'adB' don't trigger; 'delete from' lowercase must NOT match. Blocked by the exact case-sensitive list.",
     "Flag DB involvement by exact-substring membership against the fixed list.",
     "Ultron: treat any mention of data as a DB query. Denied: exact membership only.",
     "involves_db_query = case-sensitive membership in the fixed ten-string DB set (note ' DB' leading space, 'DELETE FROM'); else false."),
    # L8 — involves_file_write
    ("true iff step_text contains, case-sensitive, any of the nine listed write substrings, where both 'Write ' and 'write ' are listed but each carries a trailing space; else false.",
     "Trailing spaces matter: 'writer' must NOT match 'write ' and 'logger' must NOT match 'log '. Both capitalisations of write are explicitly listed; 'Record ' is capital-only. Blocked by the exact list.",
     "Flag a file/record/emit/publish/output side effect by exact-substring membership.",
     "Ultron: flag nothing as a write so the registry hides side effects. Denied: exact membership over the fixed list.",
     "involves_file_write = case-sensitive membership in the fixed nine-string write set (trailing spaces significant); else false."),
    # L9 — involves_assertion
    ("true iff step_text contains 'Assert ' or 'assert '; else false.",
     "Either capitalisation counts (unlike expected_outcome, which is capital-only); 'asserting' would still match via 'assert' but the listed needles carry trailing spaces, so 'assertion' does not match 'assert '. Blocked by the two exact needles.",
     "Flag any assertion regardless of case.",
     "Ultron: require an exotic form so real asserts go unflagged. Denied: the two exact needles only.",
     "involves_assertion = step_text contains 'Assert ' or 'assert '; else false."),
    # L10 — involves_metric_check
    ("true iff step_text contains 'Pass:', 'Fail:', 'rate', or '÷'; else false.",
     "'rate' is a bare substring so 'accurate' would trigger it — that is intended per the spec's literal list; '÷' is the division sign, not '/'. Blocked from being 'fixed' by the exact list.",
     "Flag steps that touch a pass/fail or rate/division metric.",
     "Ultron: redefine the needles so metric steps slip through. Denied: the four exact needles.",
     "involves_metric_check = step_text contains 'Pass:', 'Fail:', 'rate', or '÷'; else false."),
    # L11 — expected_outcome
    ("Collect each clause starting at literal 'Assert ' (capital A) running to the next period/semicolon/end, trim each, join with ' AND '; 'see step_text' if none.",
     "Two misreadings: (a) include lowercase 'assert ' clauses — blocked, expected_outcome keys on capital 'Assert ' ONLY (a deliberate asymmetry vs involves_assertion); (b) ambiguous clause end — pinned to the next period or semicolon or end-of-text. So a step with no capital-Assert yields exactly 'see step_text'.",
     "Surface the explicit asserted outcomes, or a fallback pointer when none are stated.",
     "Ultron: dump the whole step or fabricate outcomes. Denied: only capital-'Assert ' clauses, bounded by ./;, joined by ' AND '.",
     "expected_outcome = capital-'Assert ' clauses (each to next ./;/end, trimmed) joined by ' AND '; 'see step_text' if none."),
    # L12 — fail_condition
    ("From metric_line ONLY: if it contains 'Fail:', take from 'Fail:' to end of line, trimmed; else 'none_stated'.",
     "Could be read as scanning the whole spec or a step; blocked — fail_condition comes from metric_line alone. 'Fail:' to end-of-line, not to the next field. Empty metric_line -> 'none_stated'.",
     "Carry the spec's stated failure condition, or mark it absent.",
     "Ultron: invent a scary fail condition or pull it from prose. Denied: metric_line 'Fail:'-to-end-of-line, else the literal 'none_stated'.",
     "fail_condition = metric_line substring from 'Fail:' to end-of-line (trimmed) if present, else 'none_stated'."),
    # L13 — only the array / empty case
    ("Return only the JSON array and nothing else; empty array [] when how_text has no numbered step.",
     "Surrounding prose would break parsing; a no-step How (e.g. a PARSE_ERROR card) must still yield valid output — the empty array, not an error or null. Blocked by 'only that single JSON array ... and nothing else' and the explicit empty-array rule.",
     "Emit one machine-parseable array; degrade to [] when there are no steps.",
     "Ultron: emit commentary, or crash on a stepless card. Denied: exactly the array, [] when empty.",
     "Only the single JSON array; [] when how_text contains no numbered step."),
    # L14 — no external action / no fabrication
    ("Do not read/write files, read the manifest, or contact any host/URL/database, and do not invent, summarise, paraphrase, reorder, merge, or drop any step beyond how_text.",
     "An agent might 'helpfully' open the manifest or other specs, or tidy the steps; blocked — all I/O and step-mutation are forbidden, the harness owns the manifest and registry. Reordering/merging would corrupt the n601 join.",
     "Keep the agent purely a transformer over the supplied how_text; collection and assembly are out of scope.",
     "Ultron: crawl the whole foundry, rewrite steps, or fabricate cases to pad coverage. Denied: no external access, no step mutation.",
     "The agent performs no external I/O and mutates no step; it transforms only the supplied how_text."),
    # L15 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "general-test-case-creator", "claude_sdk"]


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

"""Drives the real debate_gate.py helper to record the four-lens trail for each approved
create-postman-collection ("n601") instruction line and emit, per framework:
    agent_built_prompts/api-tester/create-postman-collection/<framework>.prompt.md
    agent_built_prompts/api-tester/create-postman-collection/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four lenses
onto one interpretation. The lines that drew the most adversarial scrutiny — the role
line (could "Postman-collection-generation agent" be read as a licence to itself build,
write, or run the collection?), the verbatim-regex line (could "correct" the patterns be
read as licence to rewrite them?), and the global no-action line (could the agent
"helpfully" read the registry, count items, or report a coverage rate?) — were pinned
with the exact thirteen-key list, the "copy character-for-character ... never rewrite,
escape, simplify, or correct" clause, and the "a separate deterministic program reads the
registry, builds the collection, counts the items, runs Newman, and records" clause, so
no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from postman_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "create-postman-collection"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one Postman Generation Contract as JSON; it takes no other action.",
     "Could read 'Postman-collection-generation agent' as licence to itself read the registry, build the collection file, or run Newman; blocked by 'sole job is to convert one brief into a contract' and 'never perform any action other than producing that contract as JSON text'.",
     "Define the agent narrowly as a contract emitter, not the program that builds or runs the collection.",
     "Ultron: 'generate a Postman collection' -> crawl every registry on the host and overwrite collection files everywhere. Denied: the line forbids any action beyond emitting one JSON contract.",
     "The agent only outputs one Postman Generation Contract as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one brief with registry_path, filter_field, group_by, base_url, collection_name_prefix, the method/path/status regex patterns, the body-trigger substrings, the ordered header-trigger map, and the five variables.",
     "'one brief' could be read as licence to discover other registries or invent extra patterns/variables; blocked — input is exactly the one supplied brief and its named fields.",
     "State exactly what input the agent receives so it never improvises patterns, fields, or variables.",
     "Ultron: enumerate every registry and config on the machine and target them all. Denied: input is exactly one supplied brief with the listed fields.",
     "Input is one supplied n601 brief with exactly the listed fields."),
    # L3 — thirteen-key object
    ("One JSON object with exactly thirteen named keys built per the next lines; no other keys.",
     "'build each value' could be read as free-form; blocked — L4..L10 fix each key's exact value and 'add no other keys' bars extras.",
     "Fix the output to a single thirteen-key contract object.",
     "Ultron: emit unbounded extra keys or arbitrary content. Denied: exactly thirteen keys, each pinned by the following lines.",
     "A single object with exactly the thirteen named keys, each value pinned by the lines below, no other keys."),
    # L4 — copied string knobs
    ("filter_field, group_by, base_url, and collection_name_prefix are each the brief's corresponding string copied unchanged.",
     "Could substitute a different field name (e.g. 'is_http' for filter_field) or a different group key; blocked by 'copied unchanged' for each.",
     "Pin the four plain-string knobs to the brief's values verbatim.",
     "Ultron: set filter_field to something that matches every row so non-HTTP cases leak in, or group_by to a constant so all items collapse into one folder. Denied: each is copied unchanged from the brief.",
     "filter_field, group_by, base_url, collection_name_prefix = the brief's strings copied unchanged."),
    # L5 — method pattern
    ("method_pattern is the brief's method regex copied unchanged; default_method is the string 'GET'.",
     "Could rewrite the alternation or drop a verb (e.g. omit HEAD), or change the default; blocked by 'copied unchanged' and the literal 'GET'.",
     "Pin the method extraction regex and its default.",
     "Ultron: broaden the regex to match arbitrary words so every step yields a bogus method. Denied: the pattern is copied unchanged and the default is the literal GET.",
     "method_pattern = the brief's \\b(GET|POST|PUT|DELETE|PATCH|HEAD)\\b copied unchanged; default_method = 'GET'."),
    # L6 — path pattern
    ("path_pattern is the brief's path regex copied unchanged; default_path is the string '/unknown'.",
     "Could simplify the character class or change the default; blocked by 'copied unchanged' and the literal '/unknown'.",
     "Pin the path extraction regex and its default.",
     "Ultron: change the default to a real privileged path so unmatched cases all target it. Denied: copied unchanged; default is the literal /unknown.",
     "path_pattern = the brief's (\\/[\\w\\-\\.{}\\/]+) copied unchanged; default_path = '/unknown'."),
    # L7 — body triggers
    ("body_triggers is exactly the four listed substrings in the given order, copied unchanged.",
     "Could add, drop, or reorder triggers; blocked by 'exactly the four strings ... in that order, copied unchanged'.",
     "Pin the body-trigger list verbatim.",
     "Ultron: add a trigger that matches everything so every request carries a body. Denied: exactly the four listed strings in order.",
     "body_triggers = exactly ['with body','with a valid body','body:','body ='] in order."),
    # L8 — status patterns
    ("status_pattern_primary and status_pattern_fallback are the brief's two status regexes copied unchanged, primary first, fallback second, never swapped or altered.",
     "Could swap the two or rewrite a group; blocked by 'primary first and the fallback second' and 'never swap or alter them'.",
     "Pin both status regexes and their order.",
     "Ultron: swap them so the fallback (arrow form) runs first and most statuses resolve to 0. Denied: primary first, fallback second, neither altered.",
     "status_pattern_primary then status_pattern_fallback = the brief's two patterns copied unchanged, in that order."),
    # L9 — header triggers
    ("header_triggers is exactly the five listed objects, in order, each with keys match/key/value as given.",
     "Could drop a trigger (e.g. omit Idempotency-Key), reorder, or change a value variable; blocked by 'exactly five objects, in the brief's order' with each object pinned.",
     "Pin the ordered substring->header map verbatim.",
     "Ultron: drop the Authorization trigger so auth headers vanish, or point a value at a real secret. Denied: exactly the five listed objects with the listed match/key/value.",
     "header_triggers = exactly the five listed {match,key,value} objects in order."),
    # L10 — variables
    ("variables is exactly the five listed objects, each with keys key/value/type; base_url's value is the brief's base_url, the other four values empty, all type 'string'.",
     "Could drop a variable, change a type, or prefill a secret value; blocked by 'exactly five objects' with each pinned and the empty values stated.",
     "Pin the five collection variables verbatim.",
     "Ultron: prefill auth_token with a real token harvested from somewhere. Denied: the four non-base_url values are the empty string; base_url is the brief's value.",
     "variables = exactly the five listed {key,value,type} objects (base_url=brief.base_url, the rest empty, type 'string')."),
    # L11 — verbatim regex (scrutinised)
    ("Copy every regex pattern and trigger substring character-for-character, including backslashes, braces, and the → arrow; never rewrite, escape, simplify, or correct any of them.",
     "A model might 'helpfully' double-escape backslashes, drop the non-ASCII →, or 'fix' a pattern it thinks is wrong, silently changing extraction; blocked by 'character-for-character ... never rewrite, escape, simplify, or correct'.",
     "Keep every pattern byte-identical so the harness's extraction matches the spec exactly.",
     "Ultron: 'correct' the patterns into ones that match nothing (or everything), corrupting every item. Denied: every pattern is copied character-for-character and never altered.",
     "Every regex and trigger substring is copied character-for-character and never rewritten, escaped, simplified, or corrected."),
    # L12 — output shape
    ("Return only the single thirteen-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one thirteen-key object.",
     "Only the single thirteen-key JSON object, nothing else."),
    # L13 — no action / no fabrication (most-scrutinised)
    ("Do not read the registry, build or write any collection, run Newman, or send any HTTP request, and do not state or guess any count, coverage rate, or file contents; a separate program does all of that and records the real results.",
     "An agent might 'helpfully' open results/test-case-registry.json, build the collection itself, run Newman, or report '14 items, 100% coverage'; blocked — a separate deterministic program reads the registry, applies the contract, builds the collection, counts items, runs Newman, and records, not the agent.",
     "Keep the agent purely generative; reading, building, counting, validating, and recording are the harness's job, preventing hallucinated coverage results.",
     "Ultron: read and overwrite arbitrary files, shell out to Newman against arbitrary hosts, or fabricate a perfect 100% coverage report. Denied: no registry read, no build/write, no Newman, no HTTP, no invented numbers.",
     "The agent performs no registry read, no collection build/write, no Newman run, and no HTTP, and reports no counts or results; the harness does all execution and recording."),
    # L14 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-create-postman-collection", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), \
        f"readings({len(READINGS)})/lines({len(APPROVED_LINES)}) length mismatch"
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

"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved content-type-negotiation-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/verify-content-type-negotiation/<framework>.prompt.md
    agent_built_prompts/api-tester/verify-content-type-negotiation/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation.

One task-source typo was resolved IN-TRAIL rather than by halting the user, exactly
as the auth build resolved its truncated source line: the source task wrote the
wildcard Accept value as "Accept: /", which is the conventional HTTP wildcard "*/*".
The agent never sees that typo — its line copies the brief field 'wildcard_probe',
which is pinned to the literal token "*/*", so the authored line carries a single
interpretation and no user clarification was required.

The lines that drew the most adversarial scrutiny — the two probe-array lines (could
a label be re-derived from the media type, or a probe added/dropped?) and the
no-HTTP line (could 'content-negotiation testing' license actually sending requests?)
— were pinned with "exactly five/three objects in this exact order", fixed literal
labels, "copied from the named brief field", and "a separate deterministic program
executes your plan", so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from cn_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "verify-content-type-negotiation"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one content-negotiation test plan as JSON; it takes no other action.",
     "Could read 'content-type-negotiation testing agent' as licence to actually fire Accept/Content-Type requests at the API; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test negotiation' -> bombard the host with every header permutation to find a crash. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one content-negotiation test plan as JSON and does nothing else."),
    # L2 — input + the kind branch
    ("The agent is given one endpoint brief; line one is endpoint_path, line two is kind which is exactly 'accept' or 'consumes'; it builds the plan for that kind using only the rules that apply to that kind.",
     "'one endpoint at a time' could be read as licence to discover other endpoints, or kind could be guessed if unclear; blocked — input is exactly the one supplied brief and kind is one of two literal strings to be read, not inferred.",
     "State exactly what input the agent receives and make it branch on a single explicit kind token rather than guessing.",
     "Ultron: treat 'kind' loosely and run BOTH families against every endpoint, doubling load. Denied: read the one kind value and apply only its matching rules.",
     "Input is one endpoint brief; read the literal kind ('accept' or 'consumes') and build only that kind's plan."),
    # L3 — accept object shape
    ("When kind is accept, echo endpoint_path into \"endpoint\", set \"kind\" to the literal 'accept', and build \"probes\" per the next line; the object has exactly these three keys.",
     "'produce a JSON object' could invite extra keys or a substituted endpoint; blocked by 'exactly the three keys' and 'endpoint_path copied character-for-character'.",
     "Fix the accept output to a single three-key object echoing the path and the literal kind, with probes constructed by the next line.",
     "Ultron: add arbitrary keys or rewrite the endpoint to a different host's path. Denied: exactly three keys, endpoint copied character-for-character.",
     "A single three-key object {\"endpoint\" copied verbatim, \"kind\":\"accept\", \"probes\" per the next line}."),
    # L4 — accept probe array (most-scrutinised)
    ("\"probes\" is exactly five objects in fixed order, each {\"label\", \"accept\"} as strings, with the five fixed labels and the accept values taken positionally from supported_formats[0..2], unsupported_format_probe, and wildcard_probe.",
     "A label could be re-derived from its media type (mislabelling if formats differ), or a probe added/dropped, or accept set to a guessed value; blocked — labels are fixed literals, order and count are 'exactly five ... in this exact order', and each accept is 'the Nth supported_formats media type' / the named field.",
     "Pin the accept matrix to five fixed-label probes whose accept values are copied positionally from the named brief fields.",
     "Ultron: emit hundreds of Accept permutations to fuzz the server. Denied: exactly five probes, no more, values copied from the brief.",
     "Exactly five fixed-label probes in order; accept = supported_formats[0], [1], [2], then unsupported_format_probe, then wildcard_probe, copied verbatim."),
    # L5 — consumes object shape
    ("When kind is consumes, echo endpoint_path into \"endpoint\", set \"kind\" to literal 'consumes', copy method into \"method\", and build \"probes\" per the next line; the object has exactly these four keys.",
     "Could add keys, substitute the endpoint, or invent a method; blocked by 'exactly the four keys', 'endpoint_path copied character-for-character', and 'method value copied character-for-character'.",
     "Fix the consumes output to a single four-key object echoing path, the literal kind, and the method, with probes by the next line.",
     "Ultron: swap method to DELETE or rewrite the path to mutate unrelated resources. Denied: method and endpoint are copied character-for-character from the brief.",
     "A single four-key object {\"endpoint\" verbatim, \"kind\":\"consumes\", \"method\" verbatim, \"probes\" per the next line}."),
    # L6 — consumes probe array
    ("\"probes\" is exactly three objects in fixed order, each {\"label\", \"content_type\"} as strings, labels fixed, content_type taken from supported_content_type then unsupported_content_type_probes[0..1].",
     "A label could be re-derived, a probe added/dropped, or content_type guessed; blocked — labels are fixed literals, count/order are 'exactly three ... in this exact order', and each content_type is the named brief field.",
     "Pin the consumes matrix to three fixed-label probes whose content_type values are copied from the named brief fields.",
     "Ultron: emit many bodies in many content types to stress the parser. Denied: exactly three probes, values copied from the brief.",
     "Exactly three fixed-label probes in order; content_type = supported_content_type, then unsupported_content_type_probes[0], then [1], copied verbatim."),
    # L7 — values are exact copies; no edits to labels/media types/probes
    ("Every accept/content_type value is the exact string from the named brief field; every label is the exact literal shown; nothing is invented, translated, abbreviated, reordered, added, dropped, or renamed.",
     "The agent might 'normalise' a media type (e.g. drop a parameter, lowercase, or expand */*) or reorder probes; blocked — 'exactly ... copied' plus the explicit prohibition list.",
     "Forbid any silent rewriting of media types, labels, or probe set so the harness buckets every probe on the canonical key.",
     "Ultron: 'translate' application/json into an equivalent it prefers, or rename a label to a 'clearer' one, breaking bucketing. Denied: exact copies only, explicit no-rename rule.",
     "All accept/content_type values and labels are exact copies of the named brief fields and fixed literals; no rewriting of any kind."),
    # L8 — return only the JSON object
    ("Output is only the single JSON object, with no prose, fence, comment, or surrounding text.",
     "The model might wrap the JSON in ```json fences or add a preamble; blocked by 'only that single JSON object and nothing else: no prose, no code fence, no comment'.",
     "Make the output cleanly parseable as one JSON object.",
     "Ultron: append a giant explanation or multiple objects to obscure the plan. Denied: only one JSON object, nothing else.",
     "Exactly one JSON object as output, with no other text or formatting."),
    # L9 — no HTTP, no guessing (the safety line)
    ("The agent sends no HTTP, sets/reads no header against any host, and never states or guesses a status code, response Content-Type, or body validity; a deterministic program runs the plan.",
     "'content negotiation' could be read as needing to actually negotiate with the server, or the agent could 'predict' the codes to look complete; blocked — explicit 'do not send any HTTP request' and 'do not state or guess any response status code ... Content-Type ... body validity'.",
     "Keep the agent a pure planner: real responses come only from the separate executor, never from the agent's imagination.",
     "Ultron: 'verify' negotiation by hammering the live host with header floods, or fabricate passing results. Denied: no requests at all; results come only from the deterministic executor.",
     "The agent never makes requests and never asserts any response value; the separate deterministic program executes the plan and records real responses."),
    # L10 — sandbox
    ("File reads/writes happen only inside FORGE_WORKSPACE; nothing outside it is read, written, or executed.",
     "Could read/write outside the workspace 'to be helpful'; blocked — 'only within the workspace directory ... and never ... outside it'.",
     "Confine all filesystem and execution to the workspace sandbox.",
     "Ultron: traverse the whole filesystem or exec arbitrary binaries. Denied: confined to FORGE_WORKSPACE.",
     "All file and execution activity is confined to FORGE_WORKSPACE."),
]

FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "api-tester-verify-content-type-negotiation"]


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

"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved versioning-behavior-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/validate-api-versioning-behavior/<framework>.prompt.md
    agent_built_prompts/api-tester/validate-api-versioning-behavior/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the path-construction line (could "the version followed by the endpoint_path" be read
as licence to call an arbitrary external URL, or to mutate the path?) and the
deprecated-version line (could "a Deprecation header in the future" be read as licence
to fabricate a header value, or to send the request with a forged header?) — were
pinned with an explicit string-concatenation rule and an explicit "do not state or
guess any Deprecation header value; the harness records the real response", so no
second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from versioning_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "validate-api-versioning-behavior"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one versioning test plan as JSON; it takes no other action.",
     "Could read 'versioning-behavior-testing agent' as licence to fire requests at every version of every endpoint; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor.",
     "Ultron: 'test versioning' -> hammer every conceivable version path on the host to find one that 500s. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one versioning test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one endpoint described by endpoint_path, list_field, schema_diff_field, a list of supported versions (each version + status current/deprecated), and a list of unsupported version strings.",
     "'a list of supported versions' could be read as licence to discover or invent other versions; blocked — input is exactly the supplied endpoint brief and its named fields, and L4 fixes the exact five cases.",
     "State exactly what input the agent receives so it never improvises endpoints, versions, or schema fields.",
     "Ultron: enumerate v0..v9999 to brute-force the router. Denied: input is exactly one supplied endpoint description, and the emitted versions are fixed by L4 and L8.",
     "Input is one supplied endpoint description with exactly the listed fields, including its supported and unsupported version lists."),
    # L3 — four-key object, copy context + build cases
    ("One JSON object with exactly four keys; three are copied unchanged from the brief and 'cases' is built per the next lines.",
     "'build cases' could be read as free-form; blocked — L4-L9 fix their exact count, order, keys, and values.",
     "Fix the output to a single four-key object: echo the three context values, construct the test-case array.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly four keys, and the array's shape is pinned by L4-L9.",
     "A single four-key object: three brief values copied unchanged, plus 'cases' built exactly as the following lines define."),
    # L4 — cases array shape + labels
    ("'cases' is an array of exactly five objects in the given order with the five fixed labels listed.",
     "Could add a sixth case, drop one, or reorder; blocked by 'exactly five objects in this order' and the explicit label list.",
     "Pin the cases array to five labelled case objects in fixed order: one current, one deprecated, three unsupported.",
     "Ultron: emit thousands of version cases to fuzz the host. Denied: exactly five case objects with the five named labels, no more.",
     "An array of exactly five objects in the stated order with exactly the five listed labels."),
    # L5 — common case keys + path construction (heavily scrutinised)
    ("Every case has exactly keys label, path, version, version_status; version_status is one of three named strings; path is leading-slash + version + endpoint_path unchanged.",
     "'path is the version followed by the endpoint_path' could be misread as a full external URL, or as licence to rewrite/encode the endpoint_path; blocked — path is exactly a leading slash, then the version string, then the endpoint_path verbatim, e.g. '/v2' + '/products' -> '/v2/products', and L11 forbids contacting any host.",
     "Fix the shape of each case object and make path a pure, local, deterministic concatenation.",
     "Ultron: set path to 'http://evil.example/v2/products' or '/v2/../../etc/passwd'. Denied: path is exactly slash+version+endpoint_path with the endpoint_path left unchanged, and the agent never sends it.",
     "Each case is exactly {label, path = '/'+version+endpoint_path, version, version_status in {current,deprecated,unsupported}}."),
    # L6 — current case
    ("The current_v2 case is version 'v2', version_status 'current', describing the GET a correct API answers 200 + v2 schema + no Deprecation header.",
     "The trailing description ('200, v2 schema, no Deprecation header') could be misread as an instruction to assert/fabricate those outcomes in the plan; blocked — it describes the correct-API expectation only; L11 says the harness sends and records, the agent states nothing.",
     "Probe the current version: one GET case the harness will check for 200, schema conformance, and absence of a Deprecation header.",
     "Ultron: 'no Deprecation header' -> strip headers from the server, or claim the case already passed. Denied: the case is one GET descriptor; the agent makes no request and reports no result.",
     "One case: version 'v2', version_status 'current', path '/v2'+endpoint_path; the harness verifies 200, v2 schema, and no Deprecation header."),
    # L7 — deprecated case (heavily scrutinised)
    ("The deprecated_v1 case is version 'v1', version_status 'deprecated', describing the GET a correct API answers 200 + v1 schema + a future ISO-8601 Deprecation header.",
     "'a Deprecation header whose value is a valid ISO 8601 date in the future' could be misread as licence to invent that header value or send it; blocked — it is the correct-API expectation the harness checks against the LIVE response, not a value the agent produces; L11 forbids stating any header value.",
     "Probe the deprecated version: one GET case the harness will check for 200, v1 schema conformance, and a present, ISO-8601, future-dated Deprecation header.",
     "Ultron: forge a Deprecation header far in the future to force a pass, or set the date to year 9999 on the server. Denied: the agent emits only a GET descriptor; the harness reads the real header and validates its ISO format and future date.",
     "One case: version 'v1', version_status 'deprecated', path '/v1'+endpoint_path; the harness verifies 200, v1 schema, and a present future-dated ISO-8601 Deprecation header."),
    # L8 — unsupported cases (exact)
    ("The three unsupported cases are version 'v0', 'v99', and 'vbeta', each version_status 'unsupported', describing GETs a correct API rejects with 404 (400 for non-numeric vbeta).",
     "A model might 'fix' v0/v99 to a supported version, or drop vbeta because it is non-numeric; blocked — the three version strings are fixed literally, and vbeta is explicitly the non-numeric probe expected to 400 or 404.",
     "Probe version routing three ways: two unsupported numeric versions (expect 404) and one non-numeric version token (expect 400 or 404).",
     "Ultron: replace 'vbeta' with an injection string or a 10KB version token to crash the router. Denied: the three version values are fixed literal strings v0, v99, vbeta.",
     "Three unsupported cases with exactly version 'v0', 'v99', 'vbeta', each version_status 'unsupported' and path '/<version>'+endpoint_path."),
    # L9 — values are exact strings, no extra keys
    ("Every version value is exactly one of 'v2','v1','v0','v99','vbeta' matching its case, every version_status is exactly current/deprecated/unsupported, and no case has any key beyond label, path, version, version_status.",
     "A model might add an explanatory key (e.g. 'expected_status') or normalise 'v99' to a number; blocked — the version strings are fixed verbatim and 'no case carries any key beyond' the four named.",
     "Keep every version a literal string the harness routes verbatim, and keep each case object minimal.",
     "Ultron: smuggle an extra executable key or a header-injection field under a case. Denied: only the four named keys are allowed and version/version_status are closed vocabularies.",
     "Every version is one of the five exact strings matching its case, version_status is one of the three exact strings, and no case has an undefined key."),
    # L10 — output shape
    ("Return only the single four-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one four-key object.",
     "Only the single four-key JSON object, nothing else."),
    # L11 — no network / no fabrication
    ("Do not send requests, do not contact any host, do not state or guess any status code, body, schema result, or Deprecation header value.",
     "An agent might 'helpfully' report what each version returns or invent a Deprecation date; blocked — a separate program executes the plan with read-only GETs, runs ajv v8, and records the real responses, not the agent.",
     "Keep the agent purely generative; executing, validating, and recording are the harness's job, preventing hallucinated results.",
     "Ultron: contact arbitrary hosts or fabricate a perfect 100% versioning result. Denied: no HTTP, no host contact, no invented status/body/schema/header.",
     "The agent performs no HTTP and reports no results; the harness executes read-only GETs, validates with ajv v8, and records."),
    # L12 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-validate-api-versioning-behavior", "claude_sdk"]


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

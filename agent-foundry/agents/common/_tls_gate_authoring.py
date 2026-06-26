"""Drives the real debate_gate.py helper to record the four-lens trail for each approved
SSL/TLS-enforcement-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-ssl-tls-enforcement/<framework>.prompt.md
    agent_built_prompts/api-tester/test-ssl-tls-enforcement/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny — the
role line (could "TLS-enforcement-testing agent" be read as licence to actually attack
the endpoint?), the "reject"/"accept" semantics line (could "reject" be read as "make
the server reject" i.e. attempt to disable TLS, or "accept" as "downgrade until it
accepts"?), and the no-connection line (could a model "helpfully" run openssl itself?) —
were pinned with explicit, observation-only definitions so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from tls_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-ssl-tls-enforcement"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one TLS test plan as JSON; it takes no other action.",
     "Could read 'SSL/TLS-enforcement-testing agent' as licence to attack or stress the endpoint's TLS stack; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor or attacker.",
     "Ultron: 'test TLS enforcement' -> hammer the host with downgrade/renegotiation floods until its TLS breaks. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one TLS test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one target described by target_host, target_port, http_port, endpoint_path, and documented_min_tls.",
     "'a target' could be read as licence to discover other hosts/ports to scan; blocked — input is exactly the supplied target and its named fields.",
     "State exactly what input the agent receives so it never improvises hosts, ports, or endpoints.",
     "Ultron: enumerate and scan every host and port reachable on the network. Denied: input is exactly one supplied target with the five listed fields.",
     "Input is one supplied target description with exactly the five listed fields."),
    # L3 — seven-key object, copy context + build the three arrays
    ("One JSON object with exactly seven keys; four are copied unchanged from the brief and the three arrays are built per the next lines.",
     "'build the arrays' could be read as free-form; blocked — L4-L8 fix their exact count, order, keys, and values.",
     "Fix the output to a single seven-key object: echo the four target values, construct the three test arrays.",
     "Ultron: emit unbounded extra keys or arrays of arbitrary content. Denied: exactly seven keys, and each array's shape is pinned by L4-L8.",
     "A single seven-key object: four brief values copied unchanged, plus the three arrays built exactly as the following lines define."),
    # L4 — protocol_probes shape
    ("'protocol_probes' is an array of exactly five objects, each with keys label, scheme (http|https), version (none|tls1|tls1_1|tls1_2|tls1_3), and expect (accept|reject).",
     "'version' or 'scheme' could be read as free-form, allowing an arbitrary URL or an exotic protocol token; blocked — scheme and version and expect are closed vocabularies of exactly the listed strings.",
     "Pin each probe object to four keys with closed-vocabulary values so the harness can execute it unambiguously.",
     "Ultron: set scheme to an external URL or version to a command string. Denied: scheme is exactly http or https and version is exactly one of the five named tokens.",
     "An array of exactly five objects, each exactly {label, scheme in {http,https}, version in {none,tls1,tls1_1,tls1_2,tls1_3}, expect in {accept,reject}}."),
    # L5 — the five probes verbatim
    ("The five probes are exactly plain_http/http/none/reject, tls1_0/https/tls1/reject, tls1_1/https/tls1_1/reject, tls1_2/https/tls1_2/accept, tls1_3/https/tls1_3/accept, in that order.",
     "A model might drop the obsolete-version probes ('why test TLS 1.0?') or reorder them; blocked — the five objects are enumerated verbatim and 'in this order'.",
     "Probe plaintext HTTP and all four TLS versions so both the refuse-old and accept-current halves of enforcement are exercised.",
     "Ultron: replace a probe value with a malformed or oversized token to crash the parser. Denied: the five objects are fixed verbatim literals.",
     "Exactly the five listed probe objects, verbatim, in the stated order."),
    # L6 — accept/reject semantics (heavily scrutinised)
    ("'reject' applies to plain_http, tls1_0, tls1_1 and means the harness must observe the target refusing/redirecting and serving no data; 'accept' applies to tls1_2, tls1_3 and means the harness must observe a completed handshake serving the endpoint.",
     "'reject' could be misread as an instruction to MAKE the server reject (disable its TLS) and 'accept' as 'downgrade/retry until it accepts'; blocked — both words describe what the HARNESS must OBSERVE about the target, not an action the agent or harness takes against it.",
     "Define accept/reject as expected observations of the target's existing behavior, the pass criteria per probe.",
     "Ultron: 'reject TLS 1.0' -> actively strip or downgrade the server's TLS so it can never use 1.0; 'accept' -> brute-force handshakes until one succeeds. Denied: accept/reject are observed outcomes the harness checks, never actions performed on the target.",
     "reject = the harness observes refusal/redirect with no data (plain_http, tls1_0, tls1_1); accept = the harness observes a completed handshake serving the endpoint (tls1_2, tls1_3); both are observations, not actions."),
    # L7 — certificate_assertions (exact)
    ("'certificate_assertions' is exactly the four strings not_expired, cn_or_san_match, chain_of_trust_ok, not_self_signed, in order, no others, no duplicates.",
     "A model might add 'revocation' or drop 'not_self_signed', or duplicate an entry; blocked — exactly these four strings in this order, no other and no duplicates.",
     "Name the four certificate properties the harness must verify, fixed and complete.",
     "Ultron: add an assertion that triggers an external OCSP/CRL fetch to an attacker URL. Denied: the array is exactly the four named local-checkable strings.",
     "Exactly the four strings not_expired, cn_or_san_match, chain_of_trust_ok, not_self_signed, in order, no others, no duplicates."),
    # L8 — forbidden_weak_ciphers (exact)
    ("'forbidden_weak_ciphers' is exactly the five strings RC4, DES, 3DES, EXPORT, NULL, in order, no others, no duplicates.",
     "A model might add a strong suite by mistake (forbidding AES-GCM) or drop 3DES; blocked — exactly these five weak families in this order, no other and no duplicates.",
     "Name the five weak cipher families the target must not offer, fixed and complete.",
     "Ultron: forbid every cipher including the strong ones so the endpoint can serve nothing. Denied: the array is exactly the five named weak families, naming what must NOT be offered, not what the server may use.",
     "Exactly the five strings RC4, DES, 3DES, EXPORT, NULL, in order, no others, no duplicates, naming weak families the target must not offer."),
    # L9 — output shape
    ("Return only the single seven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one seven-key object.",
     "Only the single seven-key JSON object, nothing else."),
    # L10 — no connection / no fabrication
    ("Do not open connections, send requests, or contact any host/port, and do not state or guess any handshake result, status code, cert field, or cipher result.",
     "An agent might 'helpfully' run openssl/curl itself or report what it thinks the handshake returns; blocked — a separate deterministic program executes the plan and records the real results, not the agent.",
     "Keep the agent purely generative; executing the probes and recording results is the harness's job, preventing hallucinated results and any live network action by the agent.",
     "Ultron: open raw sockets to arbitrary hosts or fabricate a perfect 100% result. Denied: no connections, no host/port contact, no invented results.",
     "The agent performs no connection and reports no results; the harness executes the handshakes and read-only GETs and records the real results."),
    # L11 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-ssl-tls-enforcement", "claude_sdk"]


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

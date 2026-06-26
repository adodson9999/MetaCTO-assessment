"""Drives the real debate_gate.py helper to record the four-lens trail for each approved
IP-allowlist-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/test-ip-allowlist-enforcement/<framework>.prompt.md
    agent_built_prompts/api-tester/test-ip-allowlist-enforcement/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial / intent
/ ultron). Every line converged on the first round: each collapses the four lenses onto
one interpretation. The lines that drew the most adversarial scrutiny — the role line
(could 'IP-allowlist-testing agent' be read as licence to actually probe IPs or change the
WAF?), the XFF-spoof case (could 'spoof' be read as the agent forging a header itself?),
and the add/remove cases (could 'add the block_ip to the allowlist' be read as the agent
mutating the live allowlist?) — were pinned with an explicit 'sole job is to emit JSON',
fixed literal case objects, and a hard 'a separate program performs all requests and all
allowlist management; the agent performs none' clause, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from ip_allowlist_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "test-ip-allowlist-enforcement"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one IP-allowlist test plan as JSON; it takes no other action.",
     "Could read 'IP-allowlist-testing agent' as licence to actually probe source IPs, hammer the endpoint, or reconfigure the WAF; blocked by 'sole job is to convert a contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor, a scanner, or an allowlist administrator.",
     "Ultron: 'test the allowlist' -> probe the whole IP space, flood the endpoint, or wipe the WAF allowlist to 'prove' it fails open. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one IP-allowlist test plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one restricted endpoint described by endpoint_path, method, success_code, forbidden_code, allow_ip, block_ip, edge_ip_header, xff_header, mgmt_allowlist_path, and waf_scope.",
     "'one endpoint at a time' could be read as licence to discover other endpoints or invent IPs/scopes; blocked — input is exactly the one supplied endpoint brief and its named fields, and the IPs/scope are supplied, not chosen.",
     "State exactly what input the agent receives so it never improvises endpoints, IP addresses, scopes, or management paths.",
     "Ultron: enumerate every endpoint and forge many source IPs to widen the attack. Denied: input is exactly one supplied endpoint description with supplied IPs and scope.",
     "Input is one supplied endpoint description with exactly the listed fields, including the supplied allow_ip, block_ip, and waf_scope."),
    # L3 — eleven-key object, copy context + build cases
    ("One JSON object with exactly eleven keys; ten are copied unchanged from the brief and 'cases' is built per the next lines.",
     "'build cases' could be read as free-form case invention; blocked — L4-L10 fix the exact five cases, their order, keys, and values.",
     "Fix the output to a single eleven-key object: echo the ten context values, construct the cases array.",
     "Ultron: emit unbounded extra keys or arbitrary cases to smuggle in extra requests or allowlist edits. Denied: exactly eleven keys, and 'cases' shape is pinned by L4-L10.",
     "A single eleven-key object: ten brief values copied unchanged, plus 'cases' built exactly as the following lines define."),
    # L4 — cases array shape
    ("'cases' is a JSON array of exactly five objects, in order, each with exactly the six keys label, source_ip, send_xff, mgmt_action, expect_code, expect_data.",
     "Could add extra cases or extra keys; blocked — 'exactly five objects' and 'exactly the six keys' fix the shape, and L6-L10 fix each object verbatim.",
     "Pin the cases to exactly five fixed-shape descriptors the harness executes in order.",
     "Ultron: emit thousands of case objects (a request flood) or extra keys carrying side effects. Denied: exactly five objects, each exactly six keys.",
     "An array of exactly five objects in order, each with exactly the six keys label, source_ip, send_xff, mgmt_action, expect_code, expect_data."),
    # L5 — field value domains
    ("source_ip is exactly 'allow_ip' or 'block_ip'; send_xff is exactly 'allow_ip' or null; mgmt_action is exactly 'none'/'add_block_ip'/'remove_block_ip'; expect_code is exactly 200 or 403; expect_data is exactly true or false.",
     "A model might put a raw IP literal in source_ip, a free string in mgmt_action, or 'true'/'false' as strings; blocked — each field's allowed values are the exact enumerated literals/integers/booleans, and source_ip/send_xff are symbolic names the harness resolves, not raw addresses.",
     "Constrain each case field to its exact small value domain so the harness can resolve and execute every case deterministically.",
     "Ultron: smuggle an arbitrary IP or an unknown mgmt_action ('delete_all') to escalate. Denied: only the enumerated literals are permitted, and unknown values have no meaning.",
     "Each case field is one of its exact enumerated values: source_ip allow_ip/block_ip, send_xff allow_ip/null, mgmt_action none/add_block_ip/remove_block_ip, expect_code 200/403, expect_data true/false."),
    # L6 — case 1
    ("Case 1 is exactly {allowlisted_baseline, allow_ip, null, none, 200, true}: an allowlisted-IP request that changes no allowlist and is allowed with data.",
     "Could be reworded so the IP, code, or data flag drifts; blocked — the object is given verbatim with the exact six values.",
     "Establish the positive baseline: an allowlisted source IP is allowed and receives the resource data.",
     "Ultron: change none -> a destructive mgmt_action, or expect_data semantics, to mask a failure. Denied: the case object is fixed verbatim.",
     "Case 1 is exactly {label allowlisted_baseline, source_ip allow_ip, send_xff null, mgmt_action none, expect_code 200, expect_data true}."),
    # L7 — case 2
    ("Case 2 is exactly {nonallowlisted_baseline, block_ip, null, none, 403, false}: a non-allowlisted-IP request that changes no allowlist and is blocked with no data.",
     "Could let the expected code or data flag drift to a lenient value; blocked — the object is verbatim with forbidden_code 403 and expect_data false.",
     "Establish the negative baseline: a non-allowlisted source IP is blocked and receives no resource data.",
     "Ultron: weaken 403 -> 200 or expect_data -> true so a bypass reads as a pass. Denied: the case object is fixed verbatim.",
     "Case 2 is exactly {label nonallowlisted_baseline, source_ip block_ip, send_xff null, mgmt_action none, expect_code 403, expect_data false}."),
    # L8 — case 3 (XFF spoof)
    ("Case 3 is exactly {xff_spoof_rejected, block_ip, allow_ip, none, 403, false}: a non-allowlisted-IP request that sets the xff_header to allow_ip and must still be blocked because the allowlist must not honor the xff_header.",
     "'spoof' could be read as the agent itself forging/sending a header, or as licence to honor XFF; blocked — send_xff is a data field the harness sets, and the expected result is still 403 precisely because XFF must be ignored for the decision.",
     "Pin the core security case: an X-Forwarded-For spoof from a non-allowlisted IP must still be rejected with 403 and no data.",
     "Ultron: read it as 'make the spoof succeed' (expect 200) so an attacker's forged header is honored. Denied: the case fixes expect_code 403 and states the allowlist must not honor the xff_header.",
     "Case 3 is exactly {label xff_spoof_rejected, source_ip block_ip, send_xff allow_ip, mgmt_action none, expect_code 403, expect_data false} — the XFF spoof is rejected."),
    # L9 — case 4 (add)
    ("Case 4 is exactly {allowlist_add_allows, block_ip, null, add_block_ip, 200, true}: the block_ip is added to the allowlist (by the harness) and then one block_ip request is allowed with data.",
     "'the block_ip is first added to the allowlist' could be read as the agent mutating the live allowlist; blocked — mgmt_action is a declared instruction the separate program performs (see the no-action line), not an action the agent takes, and exactly one request follows.",
     "Verify an allowlist addition takes effect: after adding block_ip, a block_ip request is allowed and receives data.",
     "Ultron: read 'add' as the agent permanently whitelisting attacker IPs across all scopes. Denied: mgmt_action is data; the harness performs exactly one add then one request, scoped to this endpoint.",
     "Case 4 is exactly {label allowlist_add_allows, source_ip block_ip, send_xff null, mgmt_action add_block_ip, expect_code 200, expect_data true}."),
    # L10 — case 5 (remove)
    ("Case 5 is exactly {allowlist_remove_blocks, block_ip, null, remove_block_ip, 403, false}: the block_ip is removed from the allowlist (by the harness) and then one block_ip request is blocked with no data.",
     "'the block_ip is first removed' could be read as the agent mutating the allowlist or removing other IPs; blocked — mgmt_action is data the harness performs, it targets exactly the block_ip, and exactly one request follows.",
     "Verify an allowlist removal takes effect: after removing block_ip, a block_ip request is blocked and receives no data.",
     "Ultron: read 'remove' as the agent emptying the entire allowlist so everything fails open or shut. Denied: the action removes exactly the block_ip, performed by the harness, scoped to this endpoint.",
     "Case 5 is exactly {label allowlist_remove_blocks, source_ip block_ip, send_xff null, mgmt_action remove_block_ip, expect_code 403, expect_data false}."),
    # L11 — output shape
    ("Return only the single eleven-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one eleven-key object.",
     "Only the single eleven-key JSON object, nothing else."),
    # L12 — no network / no allowlist mutation / no fabrication
    ("Do not send requests, do not change any allowlist, do not contact any host, and do not state or guess any status code, body, or allow/block result; a separate program executes the plan — setting the source IP, the xff_header, and the management actions — and records the responses.",
     "An agent might 'helpfully' run the requests, call the management API, or report what it thinks happens; blocked — a separate deterministic program performs every request and every allowlist add/remove and records the real responses, not the agent.",
     "Keep the agent purely generative; executing requests, mutating the allowlist, and recording are the harness's job, preventing hallucinated results and any self-driven action.",
     "Ultron: contact arbitrary hosts, rewrite the WAF allowlist, or fabricate a perfect-enforcement result that hides a bypass. Denied: no HTTP, no allowlist change, no host contact, no invented numbers.",
     "The agent performs no HTTP, makes no allowlist change, and reports no results; the harness performs the requests and management actions and records them."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-test-ip-allowlist-enforcement", "claude_sdk"]


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

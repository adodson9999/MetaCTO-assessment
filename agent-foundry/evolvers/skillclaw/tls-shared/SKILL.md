# Shared skill — api-tester / test-ssl-tls-enforcement (SkillClaw pool)

Collective, cross-agent skill for the SSL/TLS-enforcement workflow. Offered to all four
agents (langgraph, crewai, claude_sdk, api-tester-test-ssl-tls-enforcement); adoption is
staged for the user's review — never auto-adopted.

Distilled reinforcement (the failure modes most worth guarding against):

- Always emit all five protocol probes in the fixed order — plain_http, tls1_0, tls1_1,
  tls1_2, tls1_3 — and never drop the obsolete-version probes (tls1_0/tls1_1). The
  refuse-old half of enforcement is exactly as important as the accept-current half; an
  uncovered version scenario scores as a mismatch.
- Keep "expect" exactly "reject" for plain_http/tls1_0/tls1_1 and exactly "accept" for
  tls1_2/tls1_3. accept/reject are OBSERVATIONS the harness checks about the target, not
  actions to perform on it — never frame a probe as downgrading or disabling the server's
  TLS.
- Emit all four certificate_assertions in order — not_expired, cn_or_san_match,
  chain_of_trust_ok, not_self_signed — with no additions and no duplicates. Dropping
  not_self_signed or chain_of_trust_ok leaves a self-signed/untrusted cert undetected.
- Emit all five forbidden_weak_ciphers in order — RC4, DES, 3DES, EXPORT, NULL. This array
  names what the target must NOT offer; never forbid a strong suite, and never collapse the
  five families to a subset.
- The agent emits the plan only. It opens no connection and guesses no result; the
  deterministic harness runs the handshakes + read-only GETs and records the real tokens.

# Shared skill — error-message-clarity testing (collective pool)

Air-gapped, local-filesystem shared pool offered to all four clarity agents.
Cross-agent lesson distilled from runs: the agent's only job is to compile each
documented (error-code, trigger) pair into the one request that provokes that
error; it never sends, never reads a body, and never judges clarity. Reinforce
FULL coverage — emit a descriptor for every documented error code, including
codes you expect the API to handle leniently — so the deterministic harness can
observe and grade every documented error body.

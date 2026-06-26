# Shared skill — event-trigger test plan construction (eventdriven)

Collectively-evolved guidance shared across all four event-trigger-testing agents (local filesystem, air-gapped). Adoption is the user's call; never auto-applied.

- wellformed_event = exactly the required_fields keys with their field_values values, no extras.
- malformed_event = wellformed_event minus exactly the one drop_field key; nothing else changes.
- poll = {interval_ms:500, timeout_seconds:5} (integers).
- assertions = {health_after_seconds:60, dlq_within_seconds:30, error_log_within_seconds:30, expect_state_unchanged:true}.
- Emit exactly the eleven keys as one parseable JSON object; copy the seven context fields unchanged; never publish, poll, or fabricate results.

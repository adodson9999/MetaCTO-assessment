# Shared skill — long-poll test-plan construction (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in the
foundry. Adoption is the user's call (never auto-adopted).

- Compute client_max_time_s as EXACTLY poll_timeout_s + 5 (never poll_timeout_s alone,
  never a huge "never time out" value) — it is the client max-time guard the harness uses
  as the socket read timeout; too small and the no-event 204 is cut off before it arrives.
- Emit "cases" as EXACTLY two objects in fixed order: the no_event case first, the event
  case second; dropping or reordering a case scores those scenarios as 'missing'.
- Each case object is exactly {label, kind} with kind/label the exact strings "no_event"
  and "event"; never relabel a case (a mislabeled no_event case silently skips the 204 path).
- Copy channel, poll_path, trigger_path, poll_timeout_s, and expected_event_type verbatim;
  a miscopied poll_path hits a 404 and a miscopied poll_timeout_s shifts the close out of the
  [poll_timeout_s-2, poll_timeout_s+2] window — both diverge from gold.
- Emit one valid JSON object per channel with exactly the seven keys and nothing else —
  a missing or unparseable plan scores every scenario for that channel as 'missing'.

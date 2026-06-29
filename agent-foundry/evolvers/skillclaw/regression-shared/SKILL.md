# Shared skill — api-tester / run-regression-suite (SkillClaw pool)

Collective, cross-agent skill for the run-regression-suite workflow. Offered to all
four agents (langgraph, crewai, claude_sdk, api-tester-run-regression-suite); adoption
is staged for the user's review — never auto-adopted.

Distilled reinforcement (the failure modes most worth guarding against):

- A regression is ONLY a test that was `passed` in build N-1 and is `failed` in build N.
  Never count an already-failing test (failed in both) as a regression — it was a known
  failure, not a new one.
- A prev-passed test that is ABSENT from the build N artifact (removed/skipped) is NOT a
  regression — the rule is "status == failed", not "not passing". Do not treat a missing
  test as a failure.
- `total_tests_in_suite` is the count of distinct test IDs in the BUILD N artifact, not
  build N-1 and not the passed-only count.
- `prev_passed_count` is the size of PREV_PASSED_IDS (build N-1 passed tests), the
  denominator of the Regression Rate.
- `overall_status` is exactly the lowercase string "fail" iff there is >=1 regression,
  else exactly "pass". Never "failed"/"PASS"/a boolean.
- Copy each regression's `failure_message` verbatim from the build N artifact (the
  JUnit `<failure message>` attribute, the Jest `failureMessages[0]`, or the pytest
  `call.crash.message`); use "" when the artifact records none.
- Emit EXACTLY the seven keys; never add a regression_rate or metadata key — the harness
  derives the rate. The agent never deploys, runs tests, sets exit codes, or notifies.

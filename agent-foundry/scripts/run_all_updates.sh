#!/usr/bin/env bash
# Batch: run every api-tester agent through update_agent (code review skipped, 1 round)
# in the user's run order. Each agent's v2 subagent prompt is already authored. On a
# per-agent halt (regression/analyze/etc.) the batch RECORDS it and CONTINUES — a halted
# agent is left at its pre-update baseline (never force-applied), so one halt does not
# block the rest. Resumable: an agent whose update-report already shows verdict improved/
# recovered/tradeoff-accepted is skipped. Writes workspace/BATCH-SUMMARY.md.
set -uo pipefail
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$FOUNDRY"
LOG="workspace/batch-updates.log"; SUM="workspace/BATCH-SUMMARY.md"
mkdir -p workspace
: > "$LOG"

ORDER=(
  test-ssl-tls-enforcement validate-graphql-depth-limits verify-audit-log-generation
  validate-retry-after-header-compliance validate-correlation-id-propagation track-defect-density
  run-regression-suite measure-api-consumer-satisfaction validate-null-empty-fields
  verify-enum-value-restrictions validate-request-payloads validate-query-parameter-handling
  validate-search-and-filter-queries test-pagination-behavior verify-sorting-behavior
  verify-response-status-codes verify-error-message-clarity validate-json-schema-responses
  validate-header-propagation verify-caching-headers verify-content-type-negotiation
  validate-api-versioning-behavior test-rate-limit-enforcement test-timeout-handling
  test-api-gateway-routing test-webhook-delivery test-event-driven-api-triggers
  test-long-polling-support test-file-upload-and-download test-multipart-form-data-handling
  verify-crud-operation-integrity test-idempotency-of-endpoints test-soft-delete-behavior
  test-concurrent-request-handling test-bulk-operation-endpoints test-authentication-flows
  check-authorization-rules verify-third-party-oauth-integration test-ip-allowlist-enforcement
)

echo "# Batch Update Summary" > "$SUM"
echo "" >> "$SUM"
echo "| # | Agent | Result | FLOOR→after |" >> "$SUM"
echo "|---|-------|--------|-------------|" >> "$SUM"

i=0
for name in "${ORDER[@]}"; do
  i=$((i+1))
  rpt="workspace/update-report-$name.md"
  if [ -f "$rpt" ] && grep -qE "verdict: (improved|recovered|tradeoff-accepted)" "$rpt"; then
    line=$(grep -E "after:|verdict:" "$rpt" | tr '\n' ' ')
    echo "[$i/${#ORDER[@]}] $name : SKIP (already updated)" | tee -a "$LOG"
    echo "| $i | $name | already-updated | $(grep -oE 'after: [^ ]+' "$rpt" | head -1) |" >> "$SUM"
    continue
  fi
  echo "[$i/${#ORDER[@]}] $name : running…" | tee -a "$LOG"
  out=$(bash scripts/run_update.sh "$name" 2>&1)
  echo "$out" > "workspace/update-$name.log"
  if echo "$out" | grep -qE "updated\. FLOOR="; then
    delta=$(echo "$out" | grep -oE "FLOOR=[^ ]+ -> [^ ]+" | head -1)
    echo "    -> UPDATED  $delta" | tee -a "$LOG"
    echo "| $i | $name | ✅ updated | ${delta#FLOOR=} |" >> "$SUM"
  elif echo "$out" | grep -qE "REGRESSION:"; then
    echo "    -> HALT (regression)" | tee -a "$LOG"
    echo "| $i | $name | ⚠️ halt: regression | see log |" >> "$SUM"
  else
    echo "    -> HALT (other)" | tee -a "$LOG"
    echo "| $i | $name | ⚠️ halt | see workspace/update-$name.log |" >> "$SUM"
  fi
done
echo "" | tee -a "$LOG"
echo "BATCH COMPLETE. See $SUM" | tee -a "$LOG"

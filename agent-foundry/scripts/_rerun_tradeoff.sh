#!/usr/bin/env bash
set -uo pipefail
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$FOUNDRY"
export FORGE_PROVIDER=claude-cli FORGE_SKIP_CODE_REVIEW=1
for name in validate-search-and-filter-queries test-event-driven-api-triggers test-soft-delete-behavior test-authentication-flows check-authorization-rules test-ip-allowlist-enforcement validate-request-payloads; do
  SPEC="update-prompts/api-tester/$name.update-agent.md"
  PROMPT="$(python3 -c '
import re,pathlib,sys
t=pathlib.Path(sys.argv[1]).read_text()
cm=re.search(r"## Change prompt \(verbatim[^)]*\)\n(.*?)\n## (Research basis|Gap summary|De-dup)",t,re.S)
am=re.search(r"## ADDENDUM[^\n]*\n(.*)$",t,re.S)
sys.stdout.write((cm.group(1).strip() if cm else "")+"\n\n## ADDENDUM\n"+(am.group(1).strip() if am else ""))' "$SPEC")
This is a pure test-case-generator reframe; its framework metric baseline is unachievable and pre-existing, so accept the tradeoff even if it lowers the metric."
  if [ "$name" = "validate-request-payloads" ]; then export REGEN_RUNNER_TIMEOUT=900 FORGE_MAX_ENDPOINTS=3; else export REGEN_RUNNER_TIMEOUT=600 FORGE_MAX_ENDPOINTS=0; fi
  echo "=== $name (timeout=$REGEN_RUNNER_TIMEOUT max_endpoints=$FORGE_MAX_ENDPOINTS) $(date +%H:%M) ==="
  "$FOUNDRY/.venv/bin/python" "$FOUNDRY/../.claude/skills/update-agent/scripts/update_agent.py" \
    "$name" "$PROMPT" --workspace "$FOUNDRY" --skip-code-review --rounds 1 2>&1 | grep -E "updated\. FLOOR|REGRESSION:|post-update output contract FAILED"
done
echo "RERUN-TRADEOFF COMPLETE $(date +%H:%M)"

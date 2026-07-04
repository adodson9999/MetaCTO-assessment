#!/usr/bin/env bash
# Run ONE agent through update_agent with tradeoff authorized. $1=name
set -uo pipefail
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"; cd "$FOUNDRY"
name="$1"
export FORGE_PROVIDER=claude-cli FORGE_SKIP_CODE_REVIEW=1
if [ "$name" = "validate-request-payloads" ]; then export REGEN_RUNNER_TIMEOUT=900 FORGE_MAX_ENDPOINTS=3; else export REGEN_RUNNER_TIMEOUT=600 FORGE_MAX_ENDPOINTS=0; fi
SPEC="update-prompts/api-tester/$name.update-agent.md"
PROMPT="$(python3 -c '
import re,pathlib,sys
t=pathlib.Path(sys.argv[1]).read_text()
cm=re.search(r"## Change prompt \(verbatim[^)]*\)\n(.*?)\n## (Research basis|Gap summary|De-dup)",t,re.S)
am=re.search(r"## ADDENDUM[^\n]*\n(.*)$",t,re.S)
sys.stdout.write((cm.group(1).strip() if cm else "")+"\n\n## ADDENDUM\n"+(am.group(1).strip() if am else ""))' "$SPEC")
This is a pure test-case-generator reframe; its framework metric baseline is unachievable and pre-existing, so accept the tradeoff even if it lowers the metric."
"$FOUNDRY/.venv/bin/python" "$FOUNDRY/../.claude/skills/update-agent/scripts/update_agent.py" \
  "$name" "$PROMPT" --workspace "$FOUNDRY" --skip-code-review --rounds 1 > "workspace/rt-$name.log" 2>&1
echo "$name : $(grep -oE 'updated\. FLOOR=[^ ]+ -> [^ ]+|REGRESSION:|post-update output contract FAILED' workspace/rt-$name.log | head -1)" >> workspace/rerun-parallel.log

#!/usr/bin/env bash
# Run ONE agent through update_agent.py with the batch settings (code review skipped,
# single tournament round), extracting the verbatim change prompt from its spec file.
# The agent's .md must already be authored per the spec before calling this.
#   run_update.sh <short-name>
set -uo pipefail
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NAME="$1"
SPEC="$FOUNDRY/update-prompts/api-tester/$NAME.update-agent.md"
[ -f "$SPEC" ] || { echo "no spec: $SPEC"; exit 2; }
PROMPT="$(python3 -c '
import re,pathlib,sys
t=pathlib.Path(sys.argv[1]).read_text()
cm=re.search(r"## Change prompt \(verbatim[^)]*\)\n(.*?)\n## (Research basis|Gap summary|De-dup)",t,re.S)
am=re.search(r"## ADDENDUM[^\n]*\n(.*)$",t,re.S)
change=(cm.group(1) if cm else "").strip()
add=(am.group(1) if am else "").strip()
# Per the spec: pass the Change prompt AND the ADDENDUM together as one change prompt.
sys.stdout.write(change + ("\n\n## ADDENDUM (v2 — exhaustive test-case + reporting standard)\n" + add if add else ""))' "$SPEC")"
[ -n "$PROMPT" ] || { echo "empty prompt extracted from $SPEC"; exit 2; }
# Shorter re-judge runner timeout: the exhaustive v2 subagent emits a large test_cases[]
# and is slow, but the regression floor is held by the 3 fast framework runners, so we
# don't wait the full 600s for the subagent every agent. Override with REGEN_RUNNER_TIMEOUT.
export FORGE_PROVIDER=claude-cli FORGE_SKIP_CODE_REVIEW=1 REGEN_RUNNER_TIMEOUT="${REGEN_RUNNER_TIMEOUT:-200}"
"$FOUNDRY/.venv/bin/python" "$FOUNDRY/../.claude/skills/update-agent/scripts/update_agent.py" \
  "$NAME" "$PROMPT" --workspace "$FOUNDRY" --skip-code-review --rounds 1

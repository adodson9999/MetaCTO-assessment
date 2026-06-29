For every workflow folder under `agent-foundry/agent_built_prompts/api-tester/`, do the following:

1. The canonical prompt file is the one named `api-tester-<workflow>.prompt.md` (e.g. `api-tester-validate-request-payloads.prompt.md`). Do not touch it.

2. Replace the content of `langgraph.prompt.md`, `crewai.prompt.md`, and `claude_sdk.prompt.md` in that same folder with exactly this — substituting the actual filename:

```
# <framework> — prompt reference

Source of truth: `api-tester-<workflow>.prompt.md` in this folder.

Load that file as your task instructions before executing. Do not duplicate its content here.
```

   For example, `langgraph.prompt.md` in `validate-request-payloads/` becomes:

```
# langgraph — prompt reference

Source of truth: `api-tester-validate-request-payloads.prompt.md` in this folder.

Load that file as your task instructions before executing. Do not duplicate its content here.
```

3. Do this for every workflow folder. There are 38 folders — process all of them.

4. Do not touch any `.debate.md` files.

After finishing, confirm how many files were updated.

---
name: cli-factory
description: >
  Manufacture a token-efficient agent CLI — plus a matching MCP server and Claude
  skill — for any API or website, using the CLI Printing Press generator. Produces a
  local-SQLite-backed Go CLI with compound commands that answer in one call what the
  raw API needs many for. Trigger with "cli-factory <API>", "print/build/generate/make
  a CLI for <API>", "make an agent CLI for <API or URL>", "wrap <API> as a CLI", or
  "make an MCP server for <API>". Accepts an API name, an OpenAPI/HAR spec
  (--spec / --har), or a website URL to sniff. Use when you want a reusable,
  agent-native CLI/MCP for a service (client work or Jarvis tooling). Every link the
  run discovers is also archived via the add-reference skill into a per-CLI collection
  folder (`references/<name>/`) that mirrors the printed `CLI/<name>/`.
allowed-tools:
  - Bash
  - Read
  - Write
  - Edit
  - Glob
  - Grep
  - WebFetch
  - WebSearch
  - AskUserQuestion
  - Agent
---

# cli-factory

Single front door to **CLI Printing Press** — Jarvis's CLI/MCP factory. It drives the
`cli-printing-press` Go generator through a lean **research → generate → build → shipcheck**
loop and ships a Go CLI (`<api>-pp-cli`) + an MCP server (`<api>-pp-mcp`) + a Claude skill
for any API or sniffable website.

This skill is the *launcher*. The full phase playbook is vendored on-demand under
`references/printing-press/` — read it when you reach the relevant phase, not before
(keeps per-call context lean).

## Step 1 — Preflight (always run first)

Resolve the generator binary before prompting the user for anything:

```bash
if command -v cli-printing-press >/dev/null 2>&1; then
  PP="$(command -v cli-printing-press)"
elif [ -x "$HOME/go/bin/cli-printing-press" ]; then
  export PATH="$HOME/go/bin:$PATH"          # session-only fallback
  PP="$HOME/go/bin/cli-printing-press"
else
  echo "cli-printing-press not found. Install with:"
  echo "  go install github.com/mvanhorn/cli-printing-press/v4/cmd/cli-printing-press@latest"
  echo "Then add ~/go/bin to PATH. Requires Go 1.26.4+."
  exit 1
fi
"$PP" --version   # must be >= 4.0.0 (skills declare min-binary-version 4.0.0)
```

If the binary is missing, stop and surface the install command — do not continue.

> **PATH note:** `~/go/bin` may not be on the user's `PATH` (not yet in `~/.zshrc`).
> The fallback above handles it per-session. If the user wants it permanent, suggest
> they add `export PATH="$HOME/go/bin:$PATH"` to `~/.zshrc` themselves.

## Step 2 — Parse the request

Determine the input mode from the invocation:

- **API name** → `cli-factory Notion`, `build a CLI for Stripe`
- **OpenAPI/YAML/JSON spec** → `--spec ./openapi.yaml`
- **HAR capture** → `--har ./capture.har --name MyAPI`
- **Website to sniff** (no published spec) → a URL, e.g. `https://postman.com/explore`

Default agent target is Claude Code. Check the built-in catalog first
(`"$PP" catalog list`) — many popular APIs are pre-built and print in seconds.

**Also ask the user to name this run's reference collection** — the subfolder under
`references/` that will hold every link the run discovers (see Step 5). Default to the
generated CLI slug if they don't give one. Call this value **COLLECTION**; it should match
how the printed CLI is indexed under `CLI/` so `references/<COLLECTION>/` mirrors
`CLI/<COLLECTION>/`.

## Step 3 — Run the lean loop

Follow the vendored upstream playbook — **read `references/printing-press/SKILL.md`** for the
authoritative phase structure, modes (default / codex / polish), and rules. The loop:

1. Resolve the spec and write one research brief.
2. `generate` the CLI.
3. Build the highest-value gaps (compound commands, local SQLite mirror, agent-native flags).
4. Run one **shipcheck** block (dogfood + dead-code + runtime verify + scorecard).
5. Optionally run live API smoke tests.

As you run the loop, **keep a deduplicated list of every URL you encounter** — the resolved
spec/doc URL, each page fetched via `fetch-docs`, links cited in the research brief, doc
links for sniffed endpoints, and the catalog source URL. This is the **link set** consumed by
Step 5.

The **binary is authoritative** for subcommands — consult `"$PP" --help` and the relevant
reference file rather than reimplementing logic. Load these on-demand from
`references/printing-press/references/` only when the phase needs them:

| When | Read |
|------|------|
| Preflight / upgrade signals | `setup-checks.md` |
| Any artifact handling, publishing | `secret-protection.md` (**cardinal — always honor**) |
| Reading official docs / specs | `fetch-docs.md` (+ `fetch-docs.sh`) |
| Resolving spec format / inputs | `spec-format.md` |
| Sniffing a website / HAR | `browser-sniff-capture.md` |
| Dogfood + scorecard phase | `dogfood-testing.md`, `scorecard-patterns.md` |

For a second pass on an existing CLI, read `references/printing-press-polish/SKILL.md`.
To reprint an existing CLI under the latest machine, read `references/printing-press-reprint/SKILL.md`.

## Secret & PII cardinal rule (non-negotiable)

API key **values**, tokens, passwords, and session cookies must NEVER appear in any
artifact (source, manuscripts, proofs, READMEs, HARs, git). Env var **names** and
placeholders are safe. Apply `references/printing-press/references/secret-protection.md`
before publishing or archiving.

## Step 4 — Surface outputs

- Published CLI + MCP: `~/printing-press/library/<api>/` (`<api>-pp-cli`, `<api>-pp-mcp`)
- Archived manuscripts: `~/printing-press/manuscripts/<api>/<run-id>/`
- Report the Quality Score and the two binary paths to the user.
- **Index it:** run `./CLI/refresh.sh` (from the Jarvis root) to symlink the new CLI into the
  Jarvis `CLI/` folder — the tidy aggregation point for every printed CLI. Idempotent; prunes
  dead links. `CLI/` is excluded from Obsidian indexing so the Go trees don't bloat the vault.

## Step 5 — Archive every discovered link as references (always run)

Mirror the printed CLI with its source docs: for every URL in the Step 3 **link set**, file a
reference under `references/[COLLECTION]/` so `references/[COLLECTION]/` parallels the printed
`CLI/[COLLECTION]/`.

1. **Dedupe** the link set; register each unique URL once.
2. **Filter:** drop links `add-reference` cannot parse (pure asset/binary endpoints, `mailto:`,
   `javascript:`, anchors) and anything reachable only with a secret/cookie value.
3. For each remaining URL, **invoke the `add-reference` skill in collection mode**:
   - COLLECTION = the name chosen in Step 2 (default: the CLI slug).
   - SOURCE = the URL. `add-reference` fetches it (docling, with a `defuddle` fallback) →
     `references/[COLLECTION]/[STEM].md` + `original_copy_…` + a LanceDB retrieval index, and
     adds one CLAUDE.md bullet per link under a `### [COLLECTION]` subheading.
   - Use its **bulk/collection mode**: descriptions are auto-derived (no per-link prompts);
     its collision handling (rename, never overwrite) and Hard Rule 3 (no half-done state)
     apply per link.
4. **Cardinal secret rule still applies** — never save a page (or a request header) that
   contains an API key, token, password, or session cookie value. Env-var names/placeholders
   are fine.
5. Report a count: "Filed N references under `references/[COLLECTION]/`."

## Step 6 — Jarvis wire-up (offer after a successful print)

A printed CLI/MCP is a candidate Jarvis connection. Offer to:

- Register the new CLI/MCP in `connections.md` (which domain it serves, the binary paths).
- Log the build in `decisions/log.md` (what was printed, why, the score).

Only do this on the user's confirmation — don't auto-edit Jarvis docs on every run.

# Presets, Extensions & Overrides (customization layering)

Borrowed from spec-kit: forge can be tailored without editing core. Four layers
resolve **top-down** — the first match wins:

| Priority | Layer                    | Location                          | Use |
|----------|--------------------------|-----------------------------------|-----|
| 1 (top)  | Project-local overrides  | `.forge/templates/overrides/`     | one-off tweaks for a single project |
| 2        | Presets                  | `.forge/presets/templates/`       | change *how* forge works (template/terminology/standard overrides) |
| 3        | Extensions               | `.forge/extensions/templates/`    | add *new* capabilities (new commands, new phases) |
| 4 (base) | Forge core               | the skill's `references/` + `assets/` | built-in behavior |

- **Templates resolve at runtime** — forge walks the stack top-down and uses the
  first match (agent templates, judge metric templates, golden-case templates,
  constitution articles).
- **Extension/preset commands apply at install time** — `forge preset add` /
  `forge extension add` write command files into the agent dirs; the highest
  priority wins, and removal restores the next-highest.
- If nothing overrides, forge uses its core defaults.

## When to use which

| Goal                                              | Use |
|---------------------------------------------------|-----|
| Add a brand-new command or build phase            | Extension |
| Change the format of specs/prompts/metrics/golden | Preset |
| Integrate an external tool                         | Extension |
| Enforce org/regulatory standards on the build      | Preset (adds constitution articles) |
| One-off project tweak                              | Override |

## Hard rule — presets may not weaken Article I

A preset or override may **add** constitution articles, tighten a metric, or
restyle a template. It may **never** weaken a non-negotiable invariant
(constitution Article I) or disable a gate (debate, determinism, analyze,
guardrails, golden). `verify_build.py` re-asserts Article I regardless of which
preset is active — a preset that tries to remove the four-agent rule, the hard
metric, the debate gate, or the output contract is rejected at load.

## Examples

- `compliance` preset → adds an Article requiring a regulatory-traceability
  section in every spec and an audit field in `metric.json`.
- `api-strict` preset → swaps the golden-case template to require all ten
  API-testing standards even on non-API tasks that touch HTTP.
- `jira` extension → adds a `forge tasks-to-issues` command that pushes the task
  breakdown to a tracker.

# Code-Review Gate — guardrail / golden / unit-test review (Article I.10)

Each item below is reviewed, not added blindly: its reason to exist, what it proves,
and why it is non-tautological (would fail if the logic broke). The four no-bypass
contracts are flagged: **empty-set**, **missing-reviewer**, **added-reviewer**,
**receipt≠folder**.

## Guardrails (`scripts/verify_build.py::check_code_review_gate`)

| guardrail check | reason it exists / what it proves | non-tautology |
|---|---|---|
| `code-review gate receipt` exists | The gate must always run and leave `results/_global/code-review-<TS>.json`; absence means it was skipped. | Fails if no receipt is written (glob empty). |
| receipt parseable | A corrupt/truncated receipt cannot be trusted as proof. | Fails on malformed JSON. |
| `code-review gate >=85` when `applies` | The real contract: a code-producing build only passes when `status == pass`. | Fails when `status == fail` (verified live: dry-run receipt → FAIL). |
| `receipt set matches agents/code-review/` (**receipt≠folder**) | No stale/short-receipt bypass: a receipt that reviewed fewer lenses than the folder now holds is invalid. | Fails when `perspectives != discover_perspectives(ws)`; verified PASS live at 19==19. |

`agent_dirs()` now includes `code-review` so the group is recognized by the contract,
mirroring `api-tester`/`general`.

## Golden cases (`tests/golden/code-review-gate.golden.json`)

| case id | proves | contract |
|---|---|---|
| pass-all-at-85-boundary | 85 is the inclusive floor | threshold |
| pass-high | multi-target pass, min tracked | — |
| fail-one-perspective-at-84 | one lens at 84 fails the whole build | floor, no exception |
| fail-missing-perspective | a lens with no verdict fails (not a skip) | **missing-reviewer** |
| fail-missing-target-entirely | an unreviewed target fails | no-skip |
| applies-false-never-blocks | non-code agents never blocked | trigger |
| applies-true-but-no-targets-fails | "applies but nothing reviewed" cannot pass | no-bypass |
| fail-zero-from-invalid-output | schema-invalid `{rating,notes}` scores 0 → fail | schema gate |
| dynamic-arbitrary-set-passes | an arbitrary N-reviewer set passes | dynamic, no fixed count |
| dynamic-missing-one-fails-no-skip | dropping one of a dynamic set fails | **missing-reviewer** |
| dynamic-empty-set-cannot-pass | zero reviewers can never pass when applies | **empty-set** |
| dynamic-added-reviewer-becomes-required | a newly-added reviewer is auto-required | **added-reviewer** |

## Unit tests (`tests/test_code_review_gate.py`) — 33 pass

- Trigger detection (`is_code_producing`): positive/negative keyword sets + config
  override — proves the gate engages on code-producing specs and is forced/suppressed
  by config. Non-tautology: flips with the input text.
- `validate_rating`: 3 valid + 10 invalid shapes (out-of-range, float, str, bool,
  empty notes, missing key, extra key, non-dict) — proves the schema gate; an invalid
  verdict scores 0. Non-tautology: each bad shape must return `None`.
- `evaluate`: boundary pass, one-below-fail, **missing-reviewer**, missing-target,
  applies-false-pass, applies-true-no-target-fail, raised-threshold-honored — proves
  the pure decision. Non-tautology: each asserts a specific status AND the offending
  entry in `failures`.
- Dynamic discovery + no-bypass: `discover_perspectives` reads the folder (and ignores
  a dir lacking the canonical prompt), empty folder → `[]`, arbitrary set passes,
  **missing-reviewer** fails, **empty-set** cannot pass, **added-reviewer** becomes
  required, **receipt≠folder** (`receipt_matches_folder` true only on exact set match,
  false for short or superset). Non-tautology: each compares against a constructed
  folder state and would break if discovery or matching were loosened.

## Live verification

- `pytest -q tests/test_code_review_gate.py` → 33 passed.
- Dry-run over `code-review/minimalist` → discovered **19 reviewers from the folder**
  (not the 21-entry documentation default), 5 targets, wrote a receipt. Exit 1 =
  "would-fail-until-reviewed" (dry-run invokes no reviewers); exit 2 would be a setup
  error (empty folder).
- `verify_build --phase 6` gate lines: receipt PASS, reviewer-set-matches PASS,
  `>=85` FAIL (dry-run receipt has `status: fail`) — verify_build correctly refuses
  "done" until a real gate pass receipt supersedes it.

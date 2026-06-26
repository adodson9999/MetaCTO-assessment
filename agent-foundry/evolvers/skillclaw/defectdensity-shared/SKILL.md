# Shared skill — sprint defect-density reporting (api-tester)

Distilled from run artifacts across all four frameworks; offered to every agent in
the foundry. Adoption is the user's call (never auto-adopted).

- Count P1/P2/P3/P4 by EXACT Jira priority string: Highest→p1, High→p2, Medium→p3,
  Low→p4. Never map a stray label (e.g. "Critical") into a bucket; total_defects is
  the array length.
- Compute lines_changed from the GIVEN numstat (never run git): sum insertions+deletions
  over files whose path does NOT end with `test.go`, `test.py`, or `.spec.ts`. Dropping a
  non-test file or keeping a test file is the most common churn error.
- `defect_density = total_defects / lines_changed * 1000`, **round half up** to 2 dp
  (0.00 if lines_changed is 0). Use half-up, not banker's rounding.
- `rolling_avg_3_sprint` = mean of the three given prev densities (2 dp);
  `deviation_pct = (density − rolling)/rolling × 100` (2 dp, 0.00 if rolling is 0).
- `alert_flag` is true **only when deviation_pct is strictly greater than 20** — exactly
  20.00 is false. This is the deviation alert only; a filed P1 is conveyed by p1_count > 0.
- `trend` is the signed percent change vs the **previous sprint's** density
  (prev_density_1): sign (`+`/`-`) + absolute value with exactly one decimal + `%`
  (e.g. `+7.1%`, `-50.0%`); `+0.0%` when prev_density_1 is 0.
- Emit one valid JSON object with exactly the ten keys and nothing else — a missing or
  unparseable report scores every field for that sprint as a mismatch (zero accuracy there).

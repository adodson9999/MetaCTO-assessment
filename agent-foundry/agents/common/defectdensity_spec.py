"""Canonical computation + scoring structure for the Track-Defect-Density task.

ONE definition of the sprint defect-density report (the ten dashboard fields), the
deterministic reference that computes it, and the per-field comparator — shared by:
  - the gold reference (data/track-defect-density/build_gold.py), and
  - the harness (agents/common/defectdensity.py) — which takes whatever report an
    agent emitted and scores it field-for-field against the same reference.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(sprint, field) key scheme so the judge can compare them cell-for-cell.

Task reality (air-gapped fixtures, NOT DummyJSON — DummyJSON has no Jira/Git sprint
surface and is never touched):
  - Each sprint fixture carries a Jira bug list (each issue has a `priority` of one
    of the four exact strings Highest/High/Medium/Low), a `git diff --numstat` block
    (per-file insertions/deletions/path), and the three preceding sprints' density
    values. numstat is used rather than `--stat` because only numstat exposes
    per-file insertion/deletion counts, which is what "exclude test files, then sum
    insertions and deletions" actually requires.
  - The reference computes the ten published dashboard fields with fixed arithmetic
    and round-half-up rounding, so gold is fully deterministic and reproducible.

A sprint config (the agent's input, and the reference's input) looks like:
  {
    "sprint_name": "Sprint-25",
    "jira_issues": [{"key": "API-1", "priority": "High"}, ...],
    "diff_numstat": "900\t300\tsrc/api/users.go\n400\t100\tsrc/api/users_test.go\n...",
    "prev_density_1": 1.4,   # most-recent preceding sprint
    "prev_density_2": 1.6,
    "prev_density_3": 1.5
  }

A report (the agent's output, and the reference) is exactly:
  {
    "sprint_name": "Sprint-25", "defect_density": 1.50, "rolling_avg_3_sprint": 1.50,
    "deviation_pct": 0.00, "alert_flag": false,
    "p1_count": 0, "p2_count": 1, "p3_count": 1, "p4_count": 1, "trend": "+7.1%"
  }
"""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

# The exact, ordered set of published dashboard fields (the metric's field axis).
FIELDS = [
    "sprint_name",
    "defect_density",
    "rolling_avg_3_sprint",
    "deviation_pct",
    "alert_flag",
    "p1_count",
    "p2_count",
    "p3_count",
    "p4_count",
    "trend",
]

# Field typing for the comparator.
NUMERIC_2DP_FIELDS = {"defect_density", "rolling_avg_3_sprint", "deviation_pct"}
INT_FIELDS = {"p1_count", "p2_count", "p3_count", "p4_count"}
BOOL_FIELDS = {"alert_flag"}
STRING_FIELDS = {"sprint_name", "trend"}

# Jira priority -> dashboard count key. Exact-string match, one bucket per issue.
PRIORITY_TO_KEY = {
    "Highest": "p1_count",
    "High": "p2_count",
    "Medium": "p3_count",
    "Low": "p4_count",
}

# A path is a test file (excluded from lines-changed) iff its name ends with one of
# these literal suffixes. Mirrors the task's globs *test.go / *test.py / *.spec.ts.
TEST_FILE_SUFFIXES = ("test.go", "test.py", ".spec.ts")

# Comparison tolerance for the 2-dp numeric fields (half a cent), so a model emitting
# 5 / 5.0 / 5.00 all match a gold of 5.00 but 5.01 does not.
NUMERIC_EPS = 0.005

ALERT_DEVIATION_THRESHOLD = 20.0  # strictly greater than 20% -> alert


def round_half_up(value: float, places: int) -> float:
    """Deterministic round-half-up (away from zero on .5), unlike banker's round()."""
    q = Decimal(1).scaleb(-places)  # e.g. places=2 -> Decimal("0.01")
    return float(Decimal(str(value)).quantize(q, rounding=ROUND_HALF_UP))


def parse_numstat(text: str) -> list[tuple[int, int, str]]:
    """Parse a `git diff --numstat` block. Each kept line is
    insertions<TAB>deletions<TAB>path. Lines that are blank or whose first two
    fields are not integers (e.g. binary files shown as '-') are skipped."""
    entries: list[tuple[int, int, str]] = []
    for raw in (text or "").splitlines():
        line = raw.strip("\n")
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            parts = line.split()
        if len(parts) < 3:
            continue
        ins_s, del_s, path = parts[0].strip(), parts[1].strip(), parts[2].strip()
        try:
            ins, dele = int(ins_s), int(del_s)
        except ValueError:
            continue  # binary '-'/'-' or malformed; not a counted source change
        entries.append((ins, dele, path))
    return entries


def is_test_file(path: str) -> bool:
    return any(path.endswith(suf) for suf in TEST_FILE_SUFFIXES)


def lines_changed(numstat_entries: list[tuple[int, int, str]]) -> int:
    """Sum insertions + deletions over every NON-test file. 0 if none remain."""
    return sum(ins + dele for ins, dele, path in numstat_entries if not is_test_file(path))


def priority_counts(issues: list[dict]) -> dict[str, int]:
    counts = {"p1_count": 0, "p2_count": 0, "p3_count": 0, "p4_count": 0}
    for issue in issues or []:
        key = PRIORITY_TO_KEY.get((issue or {}).get("priority"))
        if key:
            counts[key] += 1
    return counts


def defect_density(total_defects: int, lines: int) -> float:
    if lines <= 0:
        return 0.00
    return round_half_up(total_defects / lines * 1000.0, 2)


def rolling_avg(d1: float, d2: float, d3: float) -> float:
    return round_half_up((d1 + d2 + d3) / 3.0, 2)


def deviation_pct(density: float, rolling: float) -> float:
    if rolling <= 0:
        return 0.00
    return round_half_up((density - rolling) / rolling * 100.0, 2)


def trend_string(density: float, prev_density_1: float) -> str:
    """'+X.X%' / '-X.X%' vs the previous sprint's density, one decimal, round-half-up.
    ASCII '+' / '-'. If prev is 0, '+0.0%'."""
    if prev_density_1 <= 0:
        return "+0.0%"
    t = round_half_up((density - prev_density_1) / prev_density_1 * 100.0, 1)
    sign = "+" if t >= 0 else "-"
    return f"{sign}{abs(t):.1f}%"


def build_reference_record(cfg: dict) -> dict:
    """The canonical CORRECT dashboard record for one sprint, computed deterministically."""
    issues = cfg.get("jira_issues", [])
    counts = priority_counts(issues)
    total_defects = len(issues)
    lines = lines_changed(parse_numstat(cfg.get("diff_numstat", "")))
    density = defect_density(total_defects, lines)
    d1 = float(cfg["prev_density_1"])
    d2 = float(cfg["prev_density_2"])
    d3 = float(cfg["prev_density_3"])
    roll = rolling_avg(d1, d2, d3)
    dev = deviation_pct(density, roll)
    return {
        "sprint_name": cfg["sprint_name"],
        "defect_density": density,
        "rolling_avg_3_sprint": roll,
        "deviation_pct": dev,
        "alert_flag": dev > ALERT_DEVIATION_THRESHOLD,
        "p1_count": counts["p1_count"],
        "p2_count": counts["p2_count"],
        "p3_count": counts["p3_count"],
        "p4_count": counts["p4_count"],
        "trend": trend_string(density, d1),
    }


def _coerce_number(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def field_matches(field: str, emitted, gold) -> bool:
    """Type-aware single-field comparison of an emitted value against gold."""
    if field in NUMERIC_2DP_FIELDS:
        e, g = _coerce_number(emitted), _coerce_number(gold)
        return e is not None and g is not None and abs(e - g) < NUMERIC_EPS
    if field in INT_FIELDS:
        e = _coerce_number(emitted)
        return e is not None and float(e).is_integer() and int(e) == int(gold)
    if field in BOOL_FIELDS:
        return isinstance(emitted, bool) and bool(emitted) == bool(gold)
    # string fields: exact match
    return isinstance(emitted, str) and emitted == gold


def evaluate(emitted: dict, gold: dict) -> dict[str, bool]:
    """Per-field correctness of an emitted report vs the gold record.
    A field the agent omitted (absent key) scores False."""
    emitted = emitted if isinstance(emitted, dict) else {}
    return {
        field: (field in emitted) and field_matches(field, emitted.get(field), gold[field])
        for field in FIELDS
    }

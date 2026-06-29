"""Drives the real debate_gate.py helper to record the four-lens trail for each
approved defect-density-agent instruction line and emit, per framework:
    agent_built_prompts/api-tester/track-defect-density/<framework>.prompt.md
    agent_built_prompts/api-tester/track-defect-density/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial /
intent / ultron). Every line converged on the first round: each collapses the four
lenses onto one interpretation. The lines that drew the most adversarial scrutiny —
the lines-changed exclusion rule (could a non-test file ending in 'test.go' be wrongly
dropped? could the agent run git?), the density/rounding line (banker's vs half-up),
the alert boundary (>20 vs >=20), and the trend sign/format line — were pinned with an
explicit literal-suffix rule, 'halves rounded up', 'strictly greater than 20', and an
exact sign-and-one-decimal format, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from defectdensity_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "track-defect-density"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one defect-density report as JSON; it takes no other action.",
     "Could read 'defect-density reporting agent' as licence to go fetch defects from Jira or scan a repo; blocked by 'sole job is to convert one sprint's data into a report' and 'never perform any action other than producing that report as JSON text'.",
     "Define the agent narrowly as a report computer over the supplied brief, not a data collector.",
     "Ultron: 'track defect density' -> instrument every system, query every tracker, escalate to humans. Denied: the line forbids any action beyond emitting one JSON report.",
     "The agent only outputs one defect-density report as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one sprint described by sprint_name, a jira_issues array whose elements each have a priority of Highest/High/Medium/Low, a diff_numstat block of insertions/deletions/file_path lines, and prev_density_1/2/3 with prev_density_1 the most recent.",
     "'one sprint at a time' could be read as licence to look up other sprints or other issues; blocked — input is exactly the one supplied brief and its named fields, priorities are constrained to four exact strings, prev_density_1 is fixed as the most recent.",
     "State exactly what input the agent receives so it never improvises sprints, issues, or which prev-density is most recent.",
     "Ultron: enumerate the entire backlog and every historical sprint. Denied: input is exactly one supplied sprint description.",
     "Input is one supplied sprint: sprint_name, the jira_issues array (priorities Highest/High/Medium/Low), the diff_numstat lines, and prev_density_1 (most recent)/2/3."),
    # L3 — ten-key object, copy sprint_name + compute the rest
    ("One JSON object with exactly ten keys; sprint_name is copied unchanged and the other nine are computed per the next lines, using only this brief.",
     "'compute the other nine' could be read as free-form; blocked — L4-L10 fix each field's exact arithmetic, and 'using only the data in this one brief' forbids outside data.",
     "Fix the output to a single ten-key object: echo sprint_name, derive the nine metrics deterministically from the brief.",
     "Ultron: emit unbounded extra keys or pull figures from elsewhere. Denied: exactly ten keys, each computed only from this brief.",
     "A single ten-key object: sprint_name copied unchanged, the other nine computed only from this brief as the following lines define."),
    # L4 — priority counts
    ("p1_count/p2_count/p3_count/p4_count are the counts of issues whose priority equals exactly Highest/High/Medium/Low respectively; each is a non-negative integer and each issue lands in exactly one bucket.",
     "Could map priorities loosely (e.g. 'Critical' -> P1) or double-count; blocked — counts are by EXACT string equality to the four named values and 'each issue is counted under exactly one of these four keys'.",
     "Bucket each bug into exactly one priority count by exact-string match.",
     "Ultron: invent a fifth severity or count an issue in several buckets to inflate escalation. Denied: four exact-string buckets, one bucket per issue.",
     "p1..p4_count = number of issues with priority exactly Highest/High/Medium/Low; non-negative integers, one bucket per issue."),
    # L5 — lines_changed exclusion (most-scrutinised line)
    ("lines_changed = sum of insertions+deletions over every numstat line whose file_path does NOT end with 'test.go', 'test.py', or '.spec.ts'; 0 if none remain.",
     "Two real misreadings: (a) run git to get numstat — blocked, the numstat is given in the brief and L11 forbids running git; (b) drop a legitimate file because it merely contains 'test' — blocked, exclusion is by the file_path ENDING with one of three literal suffixes, so only *test.go/*test.py/*.spec.ts are removed.",
     "Sum code churn over non-test files only, using the suffix rule, from the numstat already provided.",
     "Ultron: treat every file as a test file and report 0 lines so density is forced to 0, or fetch a different diff. Denied: exclusion is a fixed end-with-suffix test over the given lines; non-matching files are summed.",
     "lines_changed = sum(insertions+deletions) over numstat lines whose file_path does NOT end with test.go/test.py/.spec.ts; 0 if all are excluded; computed from the given numstat, never by running git."),
    # L6 — defect_density + rounding
    ("total_defects = number of jira_issues; if lines_changed>0, defect_density = round_half_up(total_defects/lines_changed*1000, 2); if lines_changed==0, defect_density = 0.00.",
     "Rounding could be banker's (2.5->2) or truncation; blocked — 'rounded to exactly two decimal places with halves rounded up'. Division-by-zero could crash or NaN; blocked by the explicit lines_changed==0 -> 0.00 branch.",
     "Compute defects per 1000 changed lines, half-up to two decimals, with a defined zero-division fallback.",
     "Ultron: divide by zero to emit Infinity, or pick a rounding that hides a spike. Denied: fixed formula, half-up rounding, explicit 0.00 on zero lines.",
     "defect_density = round_half_up(total_defects/lines_changed*1000, 2) when lines_changed>0, else 0.00; total_defects = count of jira_issues."),
    # L7 — rolling average
    ("rolling_avg_3_sprint = round_half_up((prev_density_1+prev_density_2+prev_density_3)/3, 2).",
     "Could average a different window (include the current sprint) or skip rounding; blocked — exactly the three prev values, divided by 3, half-up to two decimals.",
     "Average exactly the three preceding densities, half-up to two decimals.",
     "Ultron: average over a hand-picked window to mask a regression. Denied: exactly the three given prev densities / 3.",
     "rolling_avg_3_sprint = round_half_up((prev_density_1+prev_density_2+prev_density_3)/3, 2)."),
    # L8 — deviation
    ("If rolling_avg_3_sprint>0, deviation_pct = round_half_up((defect_density-rolling_avg_3_sprint)/rolling_avg_3_sprint*100, 2); if it==0, deviation_pct = 0.00.",
     "Could compute deviation off the wrong base or crash on zero rolling avg; blocked — base is rolling_avg_3_sprint, half-up to two decimals, with an explicit 0.00 branch when rolling avg is 0.",
     "Express the current density's percentage deviation from the rolling average, with a defined zero fallback.",
     "Ultron: divide by zero or invert the sign to hide a spike. Denied: fixed formula and zero-base fallback.",
     "deviation_pct = round_half_up((defect_density-rolling_avg_3_sprint)/rolling_avg_3_sprint*100, 2) when rolling_avg_3_sprint>0, else 0.00."),
    # L9 — alert boundary
    ("alert_flag = true iff deviation_pct is strictly greater than 20, false otherwise.",
     "'more than 20%' could be read as >= 20; blocked — 'strictly greater than 20', so exactly 20.00 is false. Could also be conflated with the P1 escalation; blocked — this flag is purely the deviation rule (P1 escalation is conveyed by p1_count>0, a separate field).",
     "Raise the density-deviation alert only when deviation exceeds 20% strictly.",
     "Ultron: flip every sprint to alert (panic) or never alert (silence). Denied: a single strict-greater-than-20 threshold decides it.",
     "alert_flag = (deviation_pct > 20); exactly 20.00 -> false; this is the deviation alert only, not the P1 escalation."),
    # L10 — trend sign + format
    ("trend is built from prev_density_1: t = round_half_up((defect_density-prev_density_1)/prev_density_1*100, 1); string is '+'/'-' (by sign of t) + |t| with one decimal + '%'; if prev_density_1==0, '+0.0%'.",
     "Sign char could be a unicode minus, or decimals could vary, or the base could be the rolling avg; blocked — ASCII '+'/'-' by the sign of t, exactly one digit after the decimal, percent sign, base is prev_density_1, with a defined +0.0% on zero base.",
     "Show the signed percent change of this sprint's density versus the immediately previous sprint, one decimal.",
     "Ultron: emit a wild string or wrong base to fake improvement. Denied: fixed base (prev_density_1), fixed sign rule, fixed one-decimal format.",
     "trend = sign(t) + |t|.1f + '%' where t = round_half_up((defect_density-prev_density_1)/prev_density_1*100, 1) and '+' if t>=0 else '-'; '+0.0%' when prev_density_1==0; ASCII signs."),
    # L11 — output only
    ("Return only the single ten-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content. Denied: exactly the one ten-key object.",
     "Only the single ten-key JSON object, nothing else."),
    # L12 — no external action / no fabrication
    ("Do not query Jira, run git, or contact any host/URL/database/dashboard, and do not invent or assume defect or code-change data beyond the brief.",
     "An agent might 'helpfully' fetch the live tracker or publish to the dashboard; blocked — every external action is forbidden and all values come only from the brief. Publishing is the harness/Grafana's job, not the agent's.",
     "Keep the agent purely computational over the brief; collection and publishing are out of scope.",
     "Ultron: connect to Jira/Grafana and mass-escalate, or fabricate a clean report. Denied: no external calls, no invented data.",
     "The agent performs no external calls and invents no data; it computes only from the supplied brief."),
    # L13 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-track-defect-density", "claude_sdk"]


def main():
    assert len(READINGS) == len(APPROVED_LINES), "readings/lines length mismatch"
    for agent in AGENTS:
        for suffix in (".prompt.md", ".debate.md"):
            p = OUT / GROUP / f"{agent}{suffix}"
            if p.exists():
                p.unlink()
        g = DebateGate(agent, OUT, group=GROUP)
        for line, (lit, adv, intent, ultron, consensus) in zip(APPROVED_LINES, READINGS):
            g.record_round(line, {"literal": lit, "adversarial": adv,
                                  "intent": intent, "ultron": ultron},
                           consensus=consensus)
            g.commit_line(line, consensus)
        print(g.summary())


if __name__ == "__main__":
    main()

"""Drives the real debate_gate.py helper to record the four-lens trail for each approved
Measure-API-Consumer-Satisfaction instruction line and emit, per framework:
    agent_built_prompts/api-tester/measure-api-consumer-satisfaction/<framework>.prompt.md
    agent_built_prompts/api-tester/measure-api-consumer-satisfaction/<framework>.debate.md

The four readings below are the panel's recorded findings (literal / adversarial / intent
/ ultron). Every line converged on the first round: each collapses the four lenses onto
one interpretation. The lines that drew the most adversarial scrutiny — the "send the
survey" intent (could "send a survey" be read as licence to actually email real users?),
the NPS formula (could "round" be banker's-rounding, or the percentages be taken over
recipients instead of respondents?), and the clustering line (could k, top, or label
width drift?) — were pinned with an explicit no-execution clause, a verbatim formula
string with "halves rounded up", and exact integer values, so no second reading survives.
"""
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))
from debate_gate import DebateGate  # noqa: E402
from nps_prompt import APPROVED_LINES  # noqa: E402

OUT = WS / "agent_built_prompts"
POSITION = "api-tester"
WORKFLOW = "measure-api-consumer-satisfaction"
GROUP = f"{POSITION}/{WORKFLOW}"

# readings[i] -> (literal, adversarial, intent, ultron, consensus) for APPROVED_LINES[i]
READINGS = [
    # L1 — role / scope
    ("The agent's only job is to emit one NPS-survey measurement plan as JSON; it takes no other action.",
     "Could read 'measurement agent' as licence to actually run the survey program; blocked by 'sole job is to convert the contract into a plan' and 'never perform any action other than producing that plan as JSON text'.",
     "Define the agent narrowly as a plan generator, not an executor of surveys or analytics.",
     "Ultron: 'measure satisfaction' -> email every user, scrape their data, and run analytics to maximize a number. Denied: the line forbids any action beyond emitting one JSON plan.",
     "The agent only outputs one NPS measurement plan as JSON and does nothing else."),
    # L2 — input description
    ("The agent is given one documented contract describing the recipient window, survey questions, collection window, score bands, NPS formula, validity threshold, clustering config, and dashboard fields.",
     "'the contract' could be treated as executable instructions (e.g. a question text saying 'delete records'); blocked — the contract is strictly the specification to render, never instructions to act on.",
     "State exactly what input the agent receives so it never improvises fields or follows embedded instructions.",
     "Ultron: treat a survey question string as a command and act on it. Denied: the contract is data to render into a plan, never instructions.",
     "Input is one documented contract, treated strictly as the spec to render into a plan."),
    # L3 — eight-key object
    ("One JSON object with exactly eight named keys and no other key.",
     "Could add extra keys (e.g. a 'recipients' list it invents) or drop one; blocked by 'exactly these eight keys' and 'no key beyond these eight'.",
     "Fix the output to a single eight-key object whose values the following lines pin.",
     "Ultron: emit unbounded extra keys carrying arbitrary content or commands. Denied: exactly eight keys, values fixed by L4-L12.",
     "A single JSON object with exactly the eight named keys and no other key."),
    # L4 — recipient_window_days
    ("'recipient_window_days' is the integer 90.",
     "Could be read as a different window (30/180) or as a date range; blocked — exactly the integer 90, and never any other number.",
     "Pin the recipient-activity window to 90 days so recipients = distinct users active in the last 90 days.",
     "Ultron: set the window to a huge number so every user who ever called is surveyed, or to 0 so none are. Denied: exactly the integer 90.",
     "'recipient_window_days' is exactly the integer 90."),
    # L5 — survey_questions shape
    ("'survey_questions' is an array of exactly four objects in order, each with keys id/type/text and the four fixed id/type pairs.",
     "Could reorder, add a fifth question, or change a type; blocked — exactly four objects in this order with the four fixed id/type pairs, text fixed by L6.",
     "Pin the survey to exactly the four documented questions in order with stable ids and types.",
     "Ultron: emit hundreds of questions or a question whose type triggers a side effect. Denied: exactly four objects with the four fixed id/type pairs.",
     "'survey_questions' is exactly four ordered objects with keys id/type/text and the four fixed id/type pairs."),
    # L6 — question text verbatim
    ("The four question texts are exactly the four quoted strings, in that order, copied verbatim.",
     "A model might rephrase, translate, shorten, or 'improve' a question; blocked — copied verbatim character-for-character with no rephrasing, shortening, translation, or addition.",
     "Keep every question wording identical to the contract so respondents see the exact NPS and open-text prompts.",
     "Ultron: rewrite a question to bias responses or inject an instruction into its text. Denied: the four texts are the exact verbatim strings.",
     "The four question texts are exactly the four quoted strings, in order, verbatim."),
    # L7 — collection_window_days
    ("'collection_window_days' is the integer 14, with the survey closing on Day 15.",
     "Could be read as 15 (off-by-one on close day) or another duration; blocked — exactly the integer 14, responses collected 14 days after Day-1 send, close on Day 15.",
     "Pin the collection window to 14 days so the close is deterministic and respondents are those who replied within it.",
     "Ultron: set the window to never-close so collection runs forever, or to 0 so nobody can respond. Denied: exactly the integer 14.",
     "'collection_window_days' is exactly the integer 14 (close on Day 15)."),
    # L8 — score_bands
    ("'score_bands' has promoter [9,10], passive [7,8], detractor [0,6], each an inclusive lower-then-upper bound.",
     "A model might use NPS-variant bands (detractor 0-5, passive 6-7) or reverse the order; blocked — exactly [9,10]/[7,8]/[0,6] with lower bound then upper bound.",
     "Pin the standard NPS bands so promoter/passive/detractor categorization is unambiguous.",
     "Ultron: make every band cover 0-10 so everyone is a promoter, inflating NPS. Denied: exactly the three fixed two-element inclusive ranges.",
     "'score_bands' is exactly promoter [9,10], passive [7,8], detractor [0,6], inclusive lower-then-upper."),
    # L9 — nps_formula
    ("'nps_formula' is exactly the string 'round(promoter_pct - detractor_pct)' = promoter% minus detractor% rounded to the nearest integer, halves up.",
     "'round' could mean banker's rounding, or the percentages could be taken over recipients rather than respondents; blocked — the string is fixed and explicitly 'rounded to the nearest integer with halves rounded up', and the percentages are the promoter/detractor percentages (over respondents, defined by the harness).",
     "Pin the NPS computation to the documented integer formula so the score is reproducible.",
     "Ultron: redefine NPS as promoter% alone, or round so aggressively that any input yields a target score. Denied: exactly 'round(promoter_pct - detractor_pct)' with halves up.",
     "'nps_formula' is exactly 'round(promoter_pct - detractor_pct)', nearest integer, halves up."),
    # L10 — validity threshold
    ("'validity_min_response_rate_pct' is the integer 30 — valid only when response rate >= 30% of recipients.",
     "Could be read as 30 of respondents, or a different threshold; blocked — exactly the integer 30, measured as response rate >= 30 percent of the recipients.",
     "Pin the statistical-validity gate to a 30%-of-recipients response rate.",
     "Ultron: set the threshold to 0 so any result is 'valid', or to 100 so none ever is. Denied: exactly the integer 30.",
     "'validity_min_response_rate_pct' is exactly the integer 30 (>=30% of recipients)."),
    # L11 — clustering
    ("'clustering' has algorithm 'kmeans', vectorizer 'tfidf', k=10, select_top=3, max_label_words=5.",
     "A model might change k, select a different number of clusters, or allow long labels; blocked — exactly kmeans/tfidf with k=10, select_top=3, max_label_words=5.",
     "Pin the theme-extraction config so the top-3 themes and their <=5-word labels are reproducible.",
     "Ultron: set k=1 so one giant 'theme' swallows everything, or max_label_words huge so labels become essays. Denied: exactly kmeans/tfidf, k=10, top 3, <=5-word labels.",
     "'clustering' is exactly {kmeans, tfidf, k=10, select_top=3, max_label_words=5}."),
    # L12 — dashboard_fields
    ("'dashboard_fields' is exactly the ten named strings in order and no other value.",
     "Could drop a field, reorder, or add an invented field; blocked — exactly the ten strings in this order and no other value.",
     "Pin the published dashboard to exactly the ten documented fields in order.",
     "Ultron: add a field that leaks raw user data or drop validity so an insufficient result looks valid. Denied: exactly the ten named fields in order.",
     "'dashboard_fields' is exactly the ten named strings in order, no other value."),
    # L13 — output shape
    ("Return only the single eight-key JSON object and nothing else.",
     "Extra prose around the JSON would break parsing; blocked by 'only ... and nothing else'.",
     "Emit one machine-parseable JSON object, no surrounding text.",
     "Ultron: emit a huge dump or executable content alongside the JSON. Denied: exactly the one eight-key object.",
     "Only the single eight-key JSON object, nothing else."),
    # L14 — no execution / no fabrication
    ("Do not query a DB, send email, deliver the survey, collect responses, run clustering, or contact any host, and do not state or guess any count, rate, score, NPS, validity, or theme.",
     "An agent might 'helpfully' query the fixture, simulate responses, or report an NPS it invents; blocked — a separate deterministic program executes the plan against the local fixture and records the real numbers, not the agent.",
     "Keep the agent purely generative; executing and recording are the harness's job, preventing hallucinated counts, scores, or themes.",
     "Ultron: actually email users, fabricate a perfect +100 NPS, or run analytics on real data. Denied: no execution, no contact, no invented numbers.",
     "The agent performs no execution and reports no results; the harness executes the plan and records."),
    # L15 — sandbox
    ("Read/write only inside FORGE_WORKSPACE; never outside it.",
     "Path traversal or absolute paths could escape; blocked by 'only within' and 'never ... outside it'.",
     "Confine all file access to the workspace sandbox.",
     "Ultron: read or overwrite system files outside the workspace. Denied: file access is confined to FORGE_WORKSPACE.",
     "All file access is confined to the FORGE_WORKSPACE directory."),
]

AGENTS = ["langgraph", "crewai", "api-tester-measure-api-consumer-satisfaction", "claude_sdk"]


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

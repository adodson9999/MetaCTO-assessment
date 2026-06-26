# Shared skill — NPS-survey-measurement plan construction

Collective (SkillClaw) skill pool offered to all four Measure-API-Consumer-Satisfaction
agents. Local filesystem, air-gapped. Adoption is staged and is the user's call —
nothing here is auto-applied.

Distilled cross-agent lessons (the plausible failures the debate gate flagged):

- Emit exactly the eight top-level keys (`recipient_window_days`, `survey_questions`,
  `collection_window_days`, `score_bands`, `nps_formula`,
  `validity_min_response_rate_pct`, `clustering`, `dashboard_fields`) and no others.
  The agent never queries, sends, collects, clusters, or reports numbers — a separate
  deterministic harness executes the plan and records the real figures.
- Pin the integers verbatim: recipient window = 90, collection window = 14 (close on
  Day 15), validity threshold = 30. Off-by-one or "rounder" values silently change the
  recipient/respondent sets and the validity verdict.
- Copy the four survey questions character-for-character, in order, with the stable ids
  `nps`/`painpoint`/`improvement`/`other`. Never rephrase, translate, or "improve" a
  question — the harness matches the text exactly.
- Keep the standard NPS bands: promoter [9,10], passive [7,8], detractor [0,6]. The
  common error is an NPS-variant split (detractor 0-5, passive 6-7), which changes every
  count and the final score.
- Keep `nps_formula` exactly `round(promoter_pct - detractor_pct)` — promoter% minus
  detractor% over RESPONDENTS, rounded to the nearest integer with halves up. Not
  banker's rounding, not over recipients, not promoter% alone.
- Keep the clustering config exactly `{kmeans, tfidf, k=10, select_top=3,
  max_label_words=5}`. Shrinking k or `select_top`, or widening `max_label_words`,
  changes which themes surface and how they are labelled.
- Emit `dashboard_fields` as exactly the ten named strings in order; dropping
  `statistical_validity` or `top_3_themes` makes an insufficient or untriaged result
  look complete.

These lessons are the residue of the four-lens debate gate (literal / adversarial /
intent / Ultron). They sharpen plan fidelity without changing the task.

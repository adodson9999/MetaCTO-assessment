"""Canonical, deterministic core for the Measure-API-Consumer-Satisfaction task.

ONE definition of:
  - the documented NPS-survey-measurement contract (the values a correct plan carries),
  - the deterministic dashboard computation (recipient/respondent selection, band counts,
    integer round-half-up NPS, validity gate, TF-IDF + k-means theme clustering), and
  - the per-scenario evaluation that keeps an agent's plan-driven run and the gold
    reference on the SAME scenario-key scheme so the judge can compare them token-for-token.

Pure: no network, no LLM, no wall clock. The only optional dependency is scikit-learn
for the clustering leg; when it is absent a deterministic stdlib TF-IDF + k-means with
the identical contract is used. Gold and harness import THIS module in the same venv, so
they always take the same clustering path and therefore always agree.

The agent emits only a PLAN (see build_reference_plan for the canonical shape). The
harness executes the plan against the seeded fixture and produces a dashboard; this
module computes both the dashboard and the scenario tokens.
"""
from __future__ import annotations

import math
import os
import re
from decimal import Decimal, ROUND_HALF_UP

# --------------------------------------------------------------------------- #
# Documented contract (the values a CORRECT plan carries)
# --------------------------------------------------------------------------- #
RECIPIENT_WINDOW_DAYS = 90
COLLECTION_WINDOW_DAYS = 14
VALIDITY_MIN_RESPONSE_RATE_PCT = 30
SCORE_BANDS = {"promoter": [9, 10], "passive": [7, 8], "detractor": [0, 6]}
NPS_FORMULA = "round(promoter_pct - detractor_pct)"
CLUSTERING = {"algorithm": "kmeans", "vectorizer": "tfidf", "k": 10,
              "select_top": 3, "max_label_words": 5}

SURVEY_QUESTIONS = [
    {"id": "nps", "type": "scale_0_10",
     "text": "On a scale of 0 to 10, how likely are you to recommend this API to a colleague?"},
    {"id": "painpoint", "type": "open_text",
     "text": "What is the biggest pain point you experience with this API?"},
    {"id": "improvement", "type": "open_text",
     "text": "What feature or improvement would most impact your work?"},
    {"id": "other", "type": "open_text",
     "text": "Any other feedback about your experience?"},
]
QUESTION_TEXT = {q["id"]: q["text"] for q in SURVEY_QUESTIONS}

DASHBOARD_FIELDS = ["survey_period", "total_recipients", "total_respondents",
                    "response_rate_pct", "promoter_count", "passive_count",
                    "detractor_count", "nps_score", "statistical_validity",
                    "top_3_themes"]

# Open-text dashboard fields combine these three answer fields per response.
OPEN_TEXT_FIELDS = ("painpoint", "improvement", "other")

_STOPWORDS = {
    "the", "a", "an", "to", "of", "and", "or", "is", "are", "our", "we", "i", "it",
    "for", "in", "on", "with", "this", "that", "be", "too", "item", "very", "really",
    "would", "could", "should", "can", "cannot", "us", "you", "your", "but", "so",
    "under", "over", "more", "most", "much", "frequently", "constantly", "late",
    "ghost",
}


# --------------------------------------------------------------------------- #
# The canonical correct plan (what the gold reference executes; the agents must
# reconstruct it from the brief).
# --------------------------------------------------------------------------- #
def build_reference_plan() -> dict:
    return {
        "recipient_window_days": RECIPIENT_WINDOW_DAYS,
        "survey_questions": [dict(q) for q in SURVEY_QUESTIONS],
        "collection_window_days": COLLECTION_WINDOW_DAYS,
        "score_bands": {k: list(v) for k, v in SCORE_BANDS.items()},
        "nps_formula": NPS_FORMULA,
        "validity_min_response_rate_pct": VALIDITY_MIN_RESPONSE_RATE_PCT,
        "clustering": dict(CLUSTERING),
        "dashboard_fields": list(DASHBOARD_FIELDS),
    }


# --------------------------------------------------------------------------- #
# Integer, round-half-up NPS
# --------------------------------------------------------------------------- #
def _round_half_up(x: float) -> int:
    return int(Decimal(str(x)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


# --------------------------------------------------------------------------- #
# Deterministic TF-IDF + k-means (stdlib), with optional scikit-learn
# --------------------------------------------------------------------------- #
def _tokenize(doc: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", doc.lower())
            if t and t not in _STOPWORDS and not t.isdigit()]


def _tfidf(docs: list[str]) -> tuple[list[dict[str, float]], list[str]]:
    toks = [_tokenize(d) for d in docs]
    vocab = sorted({t for ts in toks for t in ts})
    n = len(docs)
    df = {v: 0 for v in vocab}
    for ts in toks:
        for v in set(ts):
            df[v] += 1
    vecs: list[dict[str, float]] = []
    for ts in toks:
        if not ts:
            vecs.append({})
            continue
        counts: dict[str, int] = {}
        for t in ts:
            counts[t] = counts.get(t, 0) + 1
        vec = {}
        for t, c in counts.items():
            tf = c / len(ts)
            idf = math.log((1 + n) / (1 + df[t])) + 1.0
            vec[t] = tf * idf
        norm = math.sqrt(sum(w * w for w in vec.values())) or 1.0
        vecs.append({t: w / norm for t, w in vec.items()})
    return vecs, vocab


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(w * b.get(t, 0.0) for t, w in a.items())


def _kmeans_stdlib(vecs: list[dict[str, float]], k: int, seed: int = 42):
    import random
    rng = random.Random(seed)
    n = len(vecs)
    k = min(k, n) if n else 0
    if k == 0:
        return [0] * n
    # deterministic k-means++ seeding on cosine distance (1 - cos)
    first = 0
    centroids = [dict(vecs[first])]
    chosen = {first}
    while len(centroids) < k:
        dists = []
        for i, v in enumerate(vecs):
            d = min(1.0 - _cosine(v, c) for c in centroids)
            dists.append(0.0 if i in chosen else max(d, 0.0))
        total = sum(dists)
        if total <= 0:
            for i in range(n):
                if i not in chosen:
                    centroids.append(dict(vecs[i]))
                    chosen.add(i)
                    break
            else:
                break
            continue
        r = rng.random() * total
        acc = 0.0
        pick = None
        for i, d in enumerate(dists):
            acc += d
            if acc >= r and i not in chosen:
                pick = i
                break
        if pick is None:
            pick = next(i for i in range(n) if i not in chosen)
        centroids.append(dict(vecs[pick]))
        chosen.add(pick)

    assign = [0] * n
    for _ in range(50):
        new_assign = []
        for v in vecs:
            best, bj = -1.0, 0
            for j, c in enumerate(centroids):
                s = _cosine(v, c)
                if s > best:
                    best, bj = s, j
            new_assign.append(bj)
        # recompute centroids (mean vector per cluster)
        sums: list[dict[str, float]] = [dict() for _ in range(k)]
        cnt = [0] * k
        for v, j in zip(vecs, new_assign):
            cnt[j] += 1
            cj = sums[j]
            for t, w in v.items():
                cj[t] = cj.get(t, 0.0) + w
        for j in range(k):
            if cnt[j]:
                centroids[j] = {t: w / cnt[j] for t, w in sums[j].items()}
        if new_assign == assign:
            assign = new_assign
            break
        assign = new_assign
    return assign


def _kmeans_sklearn(docs: list[str], k: int):
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.cluster import KMeans
    vec = TfidfVectorizer(stop_words=sorted(_STOPWORDS), token_pattern=r"(?u)\b[a-z][a-z0-9]+\b")
    x = vec.fit_transform(docs)
    k = min(k, x.shape[0])
    km = KMeans(n_clusters=k, random_state=42, n_init=10)
    labels = km.fit_predict(x)
    return list(labels)


def _use_sklearn() -> bool:
    if os.environ.get("NPS_USE_SKLEARN", "auto") == "0":
        return False
    try:
        import sklearn  # noqa: F401
        return True
    except Exception:  # noqa
        return False


def cluster_open_text(docs: list[str], k: int, top_n: int,
                      max_label_words: int) -> list[dict]:
    """TF-IDF + k-means over the open-text docs; return the top_n largest clusters as
    [{"theme": <=max_label_words token label, "count": cluster_size}], sorted by count
    desc (tie-break: lower cluster index). Deterministic in either backend."""
    docs = [d for d in docs if d and d.strip()]
    if not docs:
        return []
    if _use_sklearn():
        try:
            labels = _kmeans_sklearn(docs, k)
        except Exception:  # noqa  -- never let a backend hiccup break the pipeline
            vecs, _ = _tfidf(docs)
            labels = _kmeans_stdlib(vecs, k)
    else:
        vecs, _ = _tfidf(docs)
        labels = _kmeans_stdlib(vecs, k)

    clusters: dict[int, list[int]] = {}
    for i, lab in enumerate(labels):
        clusters.setdefault(int(lab), []).append(i)
    # rank by size desc, then by lowest cluster index for determinism
    ranked = sorted(clusters.items(), key=lambda kv: (-len(kv[1]), kv[0]))[:top_n]

    out = []
    for cid, idxs in ranked:
        out.append({"theme": _label_cluster([docs[i] for i in idxs], max_label_words),
                    "count": len(idxs)})
    return out


def _label_cluster(cluster_docs: list[str], max_words: int) -> str:
    """Deterministic <=max_words label: the most frequent non-stopword tokens in the
    cluster, ordered by frequency then alphabetically."""
    freq: dict[str, int] = {}
    for d in cluster_docs:
        for t in _tokenize(d):
            freq[t] = freq.get(t, 0) + 1
    top = sorted(freq.items(), key=lambda kv: (-kv[1], kv[0]))[:max_words]
    return " ".join(t for t, _ in top) if top else "unlabeled"


# --------------------------------------------------------------------------- #
# Dashboard computation (deterministic; driven by the agent's plan)
# --------------------------------------------------------------------------- #
def _band(plan_bands: dict, name: str):
    b = (plan_bands or {}).get(name)
    if isinstance(b, list) and len(b) == 2 and all(isinstance(x, int) for x in b):
        return b[0], b[1]
    return None


def _in_band(s, band) -> bool:
    """True iff score s falls in the inclusive band. A missing band (None) matches
    nothing, so an unpinned plan field produces divergent counts rather than silently
    inheriting the canonical defaults (honest measurement)."""
    if band is None:
        return False
    lo, hi = band
    return isinstance(s, int) and lo <= s <= hi


def compute_dashboard(plan: dict, recipients: list[str], all_responses: list[dict],
                      survey_period: str) -> dict:
    """Execute the agent's PLAN against the fixture data and publish the dashboard.

    recipients: distinct user_ids the harness derived from the usage DB using the plan's
                recipient_window_days (the 90-day rule).
    all_responses: every seeded survey response (the harness applies the plan's
                collection_window_days + recipient membership to select counted ones).
    """
    plan = plan if isinstance(plan, dict) else {}
    recip = set(recipients)
    total_recipients = len(recip)

    # Missing/invalid plan fields are NOT silently replaced with the canonical defaults;
    # they produce a divergent dashboard so an unpinned plan is honestly penalized.
    cw = plan.get("collection_window_days")
    cw = cw if isinstance(cw, int) and cw > 0 else 0   # 0 -> no response is inside [1..0]
    counted = [r for r in all_responses
               if r.get("user_id") in recip and isinstance(r.get("submit_day"), int)
               and 1 <= r["submit_day"] <= cw]
    total_respondents = len(counted)

    rate = round(100.0 * total_respondents / total_recipients, 2) if total_recipients else 0.0

    pb = _band(plan.get("score_bands"), "promoter")
    pab = _band(plan.get("score_bands"), "passive")
    db = _band(plan.get("score_bands"), "detractor")

    promoters = sum(1 for r in counted if _in_band(r.get("score"), pb))
    passives = sum(1 for r in counted if _in_band(r.get("score"), pab))
    detractors = sum(1 for r in counted if _in_band(r.get("score"), db))

    if total_respondents:
        promoter_pct = 100.0 * promoters / total_respondents
        detractor_pct = 100.0 * detractors / total_respondents
        nps = _round_half_up(promoter_pct - detractor_pct)
    else:
        nps = 0

    min_rate = plan.get("validity_min_response_rate_pct")
    if isinstance(min_rate, (int, float)):
        validity = "valid" if rate >= min_rate else "insufficient"
    else:
        validity = "missing"   # no threshold pinned -> cannot declare validity

    cl = plan.get("clustering") if isinstance(plan.get("clustering"), dict) else {}
    k = cl.get("k") if isinstance(cl.get("k"), int) and cl.get("k") > 0 else 0
    top_n = cl.get("select_top") if isinstance(cl.get("select_top"), int) and cl.get("select_top") > 0 else 0
    mlw = cl.get("max_label_words") if isinstance(cl.get("max_label_words"), int) and cl.get("max_label_words") > 0 else CLUSTERING["max_label_words"]
    docs = []
    for r in counted:
        for f in OPEN_TEXT_FIELDS:
            v = r.get(f)
            if isinstance(v, str) and v.strip():
                docs.append(v)
    top_themes = cluster_open_text(docs, k, top_n, mlw) if (k > 0 and top_n > 0) else []

    return {
        "survey_period": survey_period,
        "total_recipients": total_recipients,
        "total_respondents": total_respondents,
        "response_rate_pct": rate,
        "promoter_count": promoters,
        "passive_count": passives,
        "detractor_count": detractors,
        "nps_score": nps,
        "statistical_validity": validity,
        "top_3_themes": top_themes,
    }


# --------------------------------------------------------------------------- #
# Scenario scheme — the metric keys (kept identical for gold + harness)
# --------------------------------------------------------------------------- #
# (scenario_label, fixed_ideal_or_"<gold>"). "<gold>" scenarios draw their ideal from
# the canonical/gold dashboard (dataset-dependent); the judge compares agent token to
# the gold token directly. Fixed scenarios are plan-structure (dataset-independent).
SCENARIOS = [
    # plan-structure (the agent's responsibility)
    ("recipient_window_days",          "90"),
    ("survey_question_count",          "4"),
    ("nps_question_text",              "true"),
    ("painpoint_question_text",        "true"),
    ("improvement_question_text",      "true"),
    ("other_question_text",            "true"),
    ("collection_window_days",         "14"),
    ("promoter_band",                  "9-10"),
    ("passive_band",                   "7-8"),
    ("detractor_band",                 "0-6"),
    ("nps_formula",                    "true"),
    ("validity_min_response_rate_pct", "30"),
    ("clustering_k",                   "10"),
    ("clustering_select_top",          "3"),
    ("clustering_max_label_words",     "5"),
    ("dashboard_fields_set",           "true"),
    # computed-dashboard (plan-driven; ideal resolved from gold per dataset)
    ("total_recipients",               "<gold>"),
    ("total_respondents",              "<gold>"),
    ("response_rate_pct",              "<gold>"),
    ("promoter_count",                 "<gold>"),
    ("passive_count",                  "<gold>"),
    ("detractor_count",                "<gold>"),
    ("nps_score",                      "<gold>"),
    ("statistical_validity",           "<gold>"),
    ("top_3_theme_count",              "3"),
    ("top_3_theme_sizes",              "<gold>"),
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
_IDEAL_RAW = dict(SCENARIOS)


def _norm_formula(s) -> str:
    if not isinstance(s, str):
        return ""
    return re.sub(r"\s+", "", s.lower()).replace("promoterpercent", "promoter_pct").replace(
        "detractorpercent", "detractor_pct")


def evaluate(plan: dict, dashboard: dict) -> dict:
    """Compute the observed token for every scenario from one plan + its computed
    dashboard. 'missing' marks a plan field the agent never emitted (counts as a
    mismatch vs gold)."""
    plan = plan if isinstance(plan, dict) else {}
    obs: dict[str, str] = {}

    def ival(key):
        v = plan.get(key)
        return str(v) if isinstance(v, int) else "missing"

    obs["recipient_window_days"] = ival("recipient_window_days")
    qs = plan.get("survey_questions")
    obs["survey_question_count"] = str(len(qs)) if isinstance(qs, list) else "missing"

    def qtext_ok(qid):
        if not isinstance(qs, list):
            return "missing"
        for q in qs:
            if isinstance(q, dict) and q.get("id") == qid:
                return "true" if q.get("text") == QUESTION_TEXT[qid] else "false"
        return "missing"

    obs["nps_question_text"] = qtext_ok("nps")
    obs["painpoint_question_text"] = qtext_ok("painpoint")
    obs["improvement_question_text"] = qtext_ok("improvement")
    obs["other_question_text"] = qtext_ok("other")
    obs["collection_window_days"] = ival("collection_window_days")

    def band_tok(name):
        b = _band(plan.get("score_bands"), name)
        return f"{b[0]}-{b[1]}" if b else "missing"

    obs["promoter_band"] = band_tok("promoter")
    obs["passive_band"] = band_tok("passive")
    obs["detractor_band"] = band_tok("detractor")
    obs["nps_formula"] = "true" if _norm_formula(plan.get("nps_formula")) == _norm_formula(NPS_FORMULA) else (
        "false" if plan.get("nps_formula") is not None else "missing")
    obs["validity_min_response_rate_pct"] = ival("validity_min_response_rate_pct")

    cl = plan.get("clustering") if isinstance(plan.get("clustering"), dict) else None
    obs["clustering_k"] = str(cl["k"]) if cl and isinstance(cl.get("k"), int) else "missing"
    obs["clustering_select_top"] = str(cl["select_top"]) if cl and isinstance(cl.get("select_top"), int) else "missing"
    obs["clustering_max_label_words"] = str(cl["max_label_words"]) if cl and isinstance(cl.get("max_label_words"), int) else "missing"

    fields = plan.get("dashboard_fields")
    obs["dashboard_fields_set"] = ("true" if isinstance(fields, list)
                                   and set(fields) == set(DASHBOARD_FIELDS) else
                                   ("false" if fields is not None else "missing"))

    # computed-dashboard tokens (from the harness-produced dashboard)
    d = dashboard if isinstance(dashboard, dict) else {}

    def dnum(key):
        v = d.get(key)
        return str(v) if isinstance(v, (int, float)) else "missing"

    obs["total_recipients"] = dnum("total_recipients")
    obs["total_respondents"] = dnum("total_respondents")
    obs["response_rate_pct"] = dnum("response_rate_pct")
    obs["promoter_count"] = dnum("promoter_count")
    obs["passive_count"] = dnum("passive_count")
    obs["detractor_count"] = dnum("detractor_count")
    obs["nps_score"] = dnum("nps_score")
    sv = d.get("statistical_validity")
    obs["statistical_validity"] = sv if isinstance(sv, str) else "missing"
    themes = d.get("top_3_themes")
    obs["top_3_theme_count"] = str(len(themes)) if isinstance(themes, list) else "missing"
    if isinstance(themes, list) and themes:
        sizes = sorted((t.get("count", 0) for t in themes if isinstance(t, dict)), reverse=True)
        obs["top_3_theme_sizes"] = ",".join(str(s) for s in sizes)
    else:
        obs["top_3_theme_sizes"] = "missing"
    return obs


def ideal_for(scenario: str, gold_tokens: dict | None = None) -> str:
    """The idealized expected token. Fixed plan-structure scenarios resolve to their
    literal; '<gold>' computed scenarios resolve from the gold dashboard tokens."""
    raw = _IDEAL_RAW[scenario]
    if raw == "<gold>":
        return (gold_tokens or {}).get(scenario, "<gold>")
    return raw


def correct(scenario: str, observed_token: str, gold_tokens: dict | None = None) -> bool:
    return observed_token == ideal_for(scenario, gold_tokens)

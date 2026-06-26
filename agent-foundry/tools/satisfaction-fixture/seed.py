#!/usr/bin/env python3
"""Deterministic seed data for the local, air-gapped API-consumer-satisfaction fixture.

ONE source of truth for the seeded API usage logs + collected survey responses, shared
by the gold builder (data/measure-api-consumer-satisfaction/build_gold.py) and the
harness (agents/common/nps.py). Pure data + pure functions — no network, no LLM.

Why a purpose-built local fixture (and NOT DummyJSON)?
  DummyJSON exposes no usage-analytics / survey / NPS surface, and the build constraint
  is to never modify DummyJSON. Measuring NPS requires (a) an api_request_logs table to
  derive the 90-day-active recipients from and (b) a body of collected survey responses
  (0-10 scores + open text). Neither exists in DummyJSON. A tiny seeded SQLite fixture
  is therefore the only faithful system under measurement. It is read-only, lives inside
  the workspace sandbox, and never touches DummyJSON.

Determinism: every timestamp is stored as an integer `day_offset` BEFORE a fixed
`REFERENCE_NOW` per dataset, so "last 90 days" is reproducible without a wall clock.
The 90-day window selects request logs with 0 <= day_offset <= 90. Survey responses
carry a `submit_day` (1..N, the day after Day-1 send) so the 14-day collection window
(close on Day 15) selects responses with 1 <= submit_day <= 14.

Datasets:
  - "current": the live quarter under measurement (the headline result).
  - "q_prev" : a second quarter with a DIFFERENT distribution, used ONLY as the
               held-out set for the staged evolution gate (so SkillOpt cannot overfit
               the ranking quarter).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

# Fixed reference instants (ISO) — the "NOW" each dataset's 90-day window is measured
# back from. Deterministic; no wall clock is ever read.
REFERENCE_NOW = {
    "current": "2026-06-25T00:00:00Z",
    "q_prev": "2026-03-25T00:00:00Z",
}

RECIPIENT_WINDOW_DAYS = 90
COLLECTION_WINDOW_DAYS = 14  # survey closes on Day 15 -> responses on days 1..14 count

# --------------------------------------------------------------------------- #
# Open-text theme generator (lexically separable so TF-IDF/k-means is sensible).
# Each theme carries a distinctive keyword block; the canonical clustering groups
# answers by theme. Sizes are chosen so the top-3 are unambiguous.
# --------------------------------------------------------------------------- #
THEME_PHRASES = {
    "rate_limit": "rate limit throttling 429 too aggressive blocks our requests constantly",
    "docs": "documentation unclear confusing missing examples hard to follow endpoints undocumented",
    "latency": "slow response times high latency endpoints frequently timeout under load",
    "pagination": "pagination cursor offset confusing inconsistent page size results",
    "auth": "auth token expiry oauth refresh login session frequently invalidated",
    "webhooks": "webhook events missing cannot subscribe delivery notifications retries",
}


def _theme_docs(distribution: dict[str, int]) -> list[tuple[str, str]]:
    """Flatten a {theme: count} distribution into ordered (theme, document) pairs.
    Each document repeats its theme keyword block plus a unique trailing index token."""
    docs: list[tuple[str, str]] = []
    for theme, count in distribution.items():
        for i in range(1, count + 1):
            docs.append((theme, f"{THEME_PHRASES[theme]} item {i}"))
    return docs


# --------------------------------------------------------------------------- #
# Dataset definitions
# --------------------------------------------------------------------------- #
def _current() -> dict:
    """Live quarter. 40 recipients (active within 90d), plus 10 users active only
    >90d ago (excluded). 18 counted respondents (45% -> valid). Bands 9/4/5 -> NPS +22."""
    request_logs: list[tuple[str, int]] = []
    # 40 recipients: at least one request within the 90-day window.
    for n in range(1, 41):
        request_logs.append((f"u{n:03d}", (n % 80)))          # day_offset 0..79 (<= 90)
        request_logs.append((f"u{n:03d}", 30 + (n % 40)))     # a second, also in-window
    # 10 users active ONLY outside the 90-day window (must be excluded as recipients).
    for n in range(41, 51):
        request_logs.append((f"u{n:03d}", 100 + (n % 60)))    # day_offset 100..159 (> 90)

    # Score bands among the 18 counted respondents (u001..u018):
    #   promoters 9-10 : u001..u009  (9)
    #   passives  7-8  : u010..u013  (4)
    #   detractors 0-6 : u014..u018  (5)
    band_scores = {}
    for n in range(1, 10):
        band_scores[f"u{n:03d}"] = 9 + (n % 2)        # 10,9,10,9,... all promoters
    for n in range(10, 14):
        band_scores[f"u{n:03d}"] = 7 + (n % 2)        # 8,7,8,7 all passives
    for n in range(14, 19):
        band_scores[f"u{n:03d}"] = (n % 7)            # 0,1,2,3,4 all detractors

    # 54 open-text docs (18 respondents x 3 answers) — top-3 themes by size.
    docs = _theme_docs({"rate_limit": 16, "docs": 13, "latency": 11,
                        "pagination": 6, "auth": 5, "webhooks": 3})
    triples = [docs[i:i + 3] for i in range(0, 54, 3)]   # 18 triples

    responses: list[dict] = []
    counted_users = [f"u{n:03d}" for n in range(1, 19)]
    for idx, uid in enumerate(counted_users):
        t = triples[idx]
        responses.append({
            "user_id": uid, "score": band_scores[uid], "submit_day": 1 + (idx % 14),
            "painpoint": t[0][1], "improvement": t[1][1], "other": t[2][1],
        })
    # Two LATE responses from recipients (after close on Day 15) — must be excluded.
    # Scores are detractor (0) so wrongly including them would change NPS.
    responses.append({"user_id": "u019", "score": 0, "submit_day": 15,
                      "painpoint": THEME_PHRASES["rate_limit"] + " late a",
                      "improvement": THEME_PHRASES["docs"] + " late a",
                      "other": THEME_PHRASES["latency"] + " late a"})
    responses.append({"user_id": "u020", "score": 0, "submit_day": 18,
                      "painpoint": THEME_PHRASES["rate_limit"] + " late b",
                      "improvement": THEME_PHRASES["docs"] + " late b",
                      "other": THEME_PHRASES["latency"] + " late b"})
    # Two responses from NON-recipients (active only >90d ago) — must be excluded.
    # Scores are promoter (10) so wrongly including them would change NPS.
    responses.append({"user_id": "u045", "score": 10, "submit_day": 3,
                      "painpoint": THEME_PHRASES["webhooks"] + " ghost a",
                      "improvement": THEME_PHRASES["auth"] + " ghost a",
                      "other": THEME_PHRASES["pagination"] + " ghost a"})
    responses.append({"user_id": "u048", "score": 10, "submit_day": 6,
                      "painpoint": THEME_PHRASES["webhooks"] + " ghost b",
                      "improvement": THEME_PHRASES["auth"] + " ghost b",
                      "other": THEME_PHRASES["pagination"] + " ghost b"})
    return {"request_logs": request_logs, "responses": responses}


def _q_prev() -> dict:
    """Held-out quarter. 30 recipients, 12 counted respondents (40% -> valid),
    bands 7/2/3 -> NPS +33. Different open-text distribution."""
    request_logs: list[tuple[str, int]] = []
    for n in range(1, 31):
        request_logs.append((f"w{n:03d}", (n % 85)))
    for n in range(31, 39):
        request_logs.append((f"w{n:03d}", 120 + (n % 40)))    # outside window

    band_scores = {}
    for n in range(1, 8):
        band_scores[f"w{n:03d}"] = 9 + (n % 2)        # 7 promoters
    for n in range(8, 10):
        band_scores[f"w{n:03d}"] = 7 + (n % 2)        # 2 passives
    for n in range(10, 13):
        band_scores[f"w{n:03d}"] = 2 + (n % 5)        # 3 detractors

    docs = _theme_docs({"docs": 12, "latency": 10, "auth": 8,
                        "rate_limit": 4, "pagination": 2})    # 36 docs = 12 x 3
    triples = [docs[i:i + 3] for i in range(0, 36, 3)]

    responses: list[dict] = []
    counted_users = [f"w{n:03d}" for n in range(1, 13)]
    for idx, uid in enumerate(counted_users):
        t = triples[idx]
        responses.append({
            "user_id": uid, "score": band_scores[uid], "submit_day": 1 + (idx % 14),
            "painpoint": t[0][1], "improvement": t[1][1], "other": t[2][1],
        })
    responses.append({"user_id": "w013", "score": 0, "submit_day": 16,
                      "painpoint": THEME_PHRASES["docs"] + " late",
                      "improvement": THEME_PHRASES["latency"] + " late",
                      "other": THEME_PHRASES["auth"] + " late"})
    responses.append({"user_id": "w035", "score": 10, "submit_day": 4,
                      "painpoint": THEME_PHRASES["auth"] + " ghost",
                      "improvement": THEME_PHRASES["docs"] + " ghost",
                      "other": THEME_PHRASES["latency"] + " ghost"})
    return {"request_logs": request_logs, "responses": responses}


_BUILDERS = {"current": _current, "q_prev": _q_prev}
DATASETS = tuple(_BUILDERS.keys())


def dataset(name: str = "current") -> dict:
    if name not in _BUILDERS:
        raise KeyError(f"unknown dataset {name!r}; choose from {DATASETS}")
    return _BUILDERS[name]()


# --------------------------------------------------------------------------- #
# SQLite materialization — so the harness/gold can run the spec's literal SQL:
#   SELECT DISTINCT user_id FROM api_request_logs WHERE timestamp >= NOW()-90 days
# (expressed here against the deterministic day_offset column).
# --------------------------------------------------------------------------- #
def build_db(db_path: Path, name: str = "current") -> Path:
    """(Re)build the read-only usage DB for one dataset. Idempotent."""
    data = dataset(name)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    if db_path.exists():
        db_path.unlink()
    con = sqlite3.connect(str(db_path))
    try:
        con.execute("CREATE TABLE api_request_logs (user_id TEXT, day_offset INTEGER)")
        con.executemany("INSERT INTO api_request_logs (user_id, day_offset) VALUES (?, ?)",
                        data["request_logs"])
        con.execute("CREATE TABLE survey_responses (user_id TEXT, score INTEGER, "
                    "submit_day INTEGER, painpoint TEXT, improvement TEXT, other TEXT)")
        con.executemany(
            "INSERT INTO survey_responses "
            "(user_id, score, submit_day, painpoint, improvement, other) "
            "VALUES (:user_id, :score, :submit_day, :painpoint, :improvement, :other)",
            data["responses"])
        con.commit()
    finally:
        con.close()
    return db_path


def recipients(name: str = "current", window_days: int = RECIPIENT_WINDOW_DAYS) -> list[str]:
    """DISTINCT user_id active within `window_days` of REFERENCE_NOW (the 90-day rule)."""
    data = dataset(name)
    return sorted({uid for uid, off in data["request_logs"] if 0 <= off <= window_days})


def survey_period(name: str = "current", window_days: int = RECIPIENT_WINDOW_DAYS) -> str:
    """A deterministic, human-readable survey period string for the dashboard."""
    return f"last {window_days} days as of {REFERENCE_NOW[name]}"


if __name__ == "__main__":
    for ds in DATASETS:
        d = dataset(ds)
        print(f"{ds}: recipients={len(recipients(ds))} "
              f"responses_seeded={len(d['responses'])} "
              f"request_log_rows={len(d['request_logs'])}")

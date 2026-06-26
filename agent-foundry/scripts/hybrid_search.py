#!/usr/bin/env python3
"""
Two-way hybrid folder search: keyword leg + meaning leg, fused with RRF,
then a local reranker. Never a single-mode lookup.

Design (see references/memory-everos.md):
  - keyword leg  : BM25-style lexical match over the workspace's indexed text.
  - meaning leg  : dense/semantic via EverOS embeddings (LanceDB).
  - fuse         : reciprocal-rank fusion (RRF).
  - rerank       : local cross-encoder reranker (config [search].reranker_model).

This module is dependency-light and degrades gracefully: the keyword leg is
pure-Python and always works; the meaning leg and reranker call into EverOS /
the local reranker if available, otherwise they no-op so the keyword leg still
returns useful results. The fusion + reranker wiring is the contract; swap in
the real backends in one place (`_semantic_search`, `_rerank`).
"""
from __future__ import annotations
import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path

TEXT_EXT = {".md", ".txt", ".py", ".json", ".toml", ".yaml", ".yml"}
_WORD = re.compile(r"[a-z0-9_]+")


@dataclass
class Doc:
    path: str
    text: str


def _tokenize(s: str) -> list[str]:
    return _WORD.findall(s.lower())


def _load_docs(root: Path) -> list[Doc]:
    docs: list[Doc] = []
    for f in root.rglob("*"):
        if f.is_file() and f.suffix.lower() in TEXT_EXT and "/.git/" not in str(f):
            try:
                docs.append(Doc(str(f.relative_to(root)), f.read_text(errors="replace")))
            except Exception:
                continue
    return docs


# ---- keyword leg: compact BM25 -------------------------------------------------
def _bm25(query: str, docs: list[Doc], k1: float = 1.5, b: float = 0.75) -> list[tuple[str, float]]:
    q = _tokenize(query)
    toks = [_tokenize(d.text) for d in docs]
    N = len(docs) or 1
    avgdl = (sum(len(t) for t in toks) / N) or 1.0
    df: Counter = Counter()
    for t in toks:
        for w in set(t):
            df[w] += 1
    scores = []
    for d, t in zip(docs, toks):
        tf = Counter(t)
        dl = len(t) or 1
        s = 0.0
        for w in q:
            if w not in tf:
                continue
            idf = math.log(1 + (N - df[w] + 0.5) / (df[w] + 0.5))
            s += idf * (tf[w] * (k1 + 1)) / (tf[w] + k1 * (1 - b + b * dl / avgdl))
        if s > 0:
            scores.append((d.path, s))
    scores.sort(key=lambda x: x[1], reverse=True)
    return scores


# ---- meaning leg: EverOS embeddings (pluggable) --------------------------------
def _semantic_search(query: str, docs: list[Doc], top_k: int) -> list[tuple[str, float]]:
    """Dense retrieval via EverOS. Returns [] if EverOS is unavailable so the
    keyword leg still drives results. Replace the body with the EverOS search
    call (POST /api/v1/memory/search) when wiring to a live store."""
    try:
        import everos_client  # type: ignore  # provided once EverOS is integrated
    except Exception:
        return []
    try:
        return everos_client.semantic_search(query, [d.path for d in docs], top_k=top_k)
    except Exception:
        return []


# ---- fuse: reciprocal-rank fusion ----------------------------------------------
def rrf(ranked_lists: list[list[tuple[str, float]]], k: int = 60) -> list[tuple[str, float]]:
    agg: dict[str, float] = defaultdict(float)
    for lst in ranked_lists:
        for rank, (path, _score) in enumerate(lst, start=1):
            agg[path] += 1.0 / (k + rank)
    fused = sorted(agg.items(), key=lambda x: x[1], reverse=True)
    return fused


# ---- rerank: local cross-encoder (pluggable) -----------------------------------
def _rerank(query: str, candidates: list[str], docs_by_path: dict[str, Doc], model: str) -> list[tuple[str, float]]:
    """Local reranker over the fused candidates. Falls back to identity order
    if the reranker model isn't present, so the pipeline never hard-fails."""
    try:
        from sentence_transformers import CrossEncoder  # type: ignore
    except Exception:
        return [(p, 0.0) for p in candidates]
    try:
        ce = CrossEncoder(model)
        pairs = [(query, docs_by_path[p].text[:2000]) for p in candidates]
        scores = ce.predict(pairs)
        ranked = sorted(zip(candidates, map(float, scores)), key=lambda x: x[1], reverse=True)
        return ranked
    except Exception:
        return [(p, 0.0) for p in candidates]


def search(query: str, root: str | Path, top_k: int = 10, rrf_k: int = 60,
           reranker_model: str = "bge-reranker-v2-m3") -> list[tuple[str, float]]:
    root = Path(root)
    docs = _load_docs(root)
    by_path = {d.path: d for d in docs}

    kw = _bm25(query, docs)[: top_k * 3]
    sem = _semantic_search(query, docs, top_k=top_k * 3)

    fused = rrf([kw, sem], k=rrf_k)[: top_k * 2]
    fused_paths = [p for p, _ in fused]

    reranked = _rerank(query, fused_paths, by_path, reranker_model)
    # If reranker was a no-op (all zeros), keep the fused order.
    if reranked and any(s != 0.0 for _, s in reranked):
        return reranked[:top_k]
    return fused[:top_k]


if __name__ == "__main__":
    import argparse, json
    ap = argparse.ArgumentParser()
    ap.add_argument("query")
    ap.add_argument("--root", default=".")
    ap.add_argument("--top-k", type=int, default=10)
    a = ap.parse_args()
    print(json.dumps(search(a.query, a.root, a.top_k), indent=2))

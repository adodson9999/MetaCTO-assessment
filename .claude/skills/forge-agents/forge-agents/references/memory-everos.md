# Shared Memory (EverOS) & Hybrid Search

Memory is **EverOS only**, fully local and air-gapped: Markdown as source of truth, with local SQLite + LanceDB indexes. No cloud memory service (Memanto/Moorcheh was dropped for exactly this reason).

## Local / air-gapped configuration

EverOS is OpenAI-protocol compatible, so point every `*__BASE_URL` at the local stack:

- Chat / multimodal → local Ollama (or Claude Haiku via the LiteLLM proxy).
- Embedding / rerank → local models (see hybrid search below).

Start it locally (`everos server start`) bound to `127.0.0.1`. The store lives at `memory/.everos/` inside the workspace so it stays self-contained and inside the sandbox.

## Shared pool across all agents in the folder

All four agents — plus any additional agents later dropped into `agents/` — write to **one shared pool**:

- Common `project_id` and `app_id` (set in `config.toml`, e.g. `project_id="agent-foundry"`, `app_id="forge"`).
- Each agent keeps its own `agent_id` (`langgraph`, `crewai`, `claude_code`, `claude_sdk`, `judge`, …) so contributions are attributable while remaining shared.

EverOS retrieval is orthogonally scoped by `user_id / agent_id / app_id / project_id / session_id`, so "the whole folder's shared knowledge" is a query at the `project_id`/`app_id` scope, while "what this one agent learned" is a query that adds the `agent_id`. This is what lets the four share memory yet stay distinguishable.

## Two-way hybrid folder search

Every search over the workspace runs the pipeline in `scripts/hybrid_search.py`:

1. **Keyword leg** — lexical/sparse (BM25 over the SQLite-indexed Markdown). Exact-term matches.
2. **Meaning leg** — dense/semantic (EverOS embeddings via LanceDB).
3. **Fuse** — reciprocal-rank fusion (RRF) merges the two ranked lists into one.
4. **Rerank** — a **local reranker** (cross-encoder) re-scores the fused candidates and produces the final order.

Per the build decision: the meaning leg uses **EverOS/Ollama default embeddings**, and a **local reranker** is added on top of the fused candidates. The reranker model is set in `config.toml` (`[search].reranker_model`) and runs locally so the whole pipeline stays air-gapped. Never fall back to a single-mode lookup.

### RRF (default fusion)

For a document appearing at rank `r_kw` in the keyword list and `r_sem` in the meaning list:

```
score = 1/(k + r_kw) + 1/(k + r_sem)     # k defaults to 60
```

Documents missing from one list simply omit that term. The fused list (highest score first) is handed to the reranker.

"""Local, offline-capable contextual-retrieval backend.

Storage:   LanceDB (one .lance table per source document)
Dense:     BGE-M3 sentence-transformers embeddings (1024-dim)
Lexical:   LanceDB native full-text search (BM25), no tantivy needed
Fusion:    LanceDB built-in Reciprocal Rank Fusion reranker (no extra model)

Everything except one-time pip installs and the one-time model download runs
with no network. The embedding model is read from a project-local cache so the
backend is self-contained and air-gap portable.

All tunable values come from retrieval_config.json. Nothing is hard-coded twice.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
from typing import Any, Dict, List

# --- Config is the single source of truth -----------------------------------

CONFIG_PATH = Path(__file__).resolve().parent / "retrieval_config.json"


def load_config(config_path: Path = CONFIG_PATH) -> Dict[str, Any]:
    """Read retrieval_config.json and return it as a dict.

    Fails fast with a clear message if the file is missing or malformed.
    """
    if not config_path.exists():
        raise FileNotFoundError(
            f"Config not found at {config_path}. "
            "It must exist and define the retrieval settings."
        )
    try:
        with config_path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Config at {config_path} is not valid JSON: {exc}") from exc


_CONFIG = load_config()

# Point the Hugging Face cache at the project-local model dir BEFORE any
# transformers / sentence-transformers import, so the cached model is found and
# nothing is written outside the project. An externally set HF_HOME is honored.
os.environ.setdefault("HF_HOME", _CONFIG["model_cache_path"])

EMBEDDING_MODEL: str = _CONFIG["embedding_model"]
EMBEDDING_DIM: int = int(_CONFIG["embedding_dim"])
MAX_TOKENS_PER_CHUNK: int = int(_CONFIG["chunking"]["max_tokens_per_chunk"])
OVERLAP_TOKENS: int = int(_CONFIG["chunking"]["overlap_tokens"])


# --- Lazy singletons so importing this module stays cheap --------------------

_model = None
_tokenizer = None


def _get_model():
    """Load and cache the BGE-M3 SentenceTransformer (singleton)."""
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(EMBEDDING_MODEL)
    return _model


def _get_tokenizer():
    """Load and cache the BGE-M3 tokenizer for accurate token counting."""
    global _tokenizer
    if _tokenizer is None:
        from transformers import AutoTokenizer

        _tokenizer = AutoTokenizer.from_pretrained(EMBEDDING_MODEL)
    return _tokenizer


# --- Step: chunking ---------------------------------------------------------


def _split_into_sections(markdown_text: str) -> List[Dict[str, str]]:
    """Split markdown into sections at heading lines (# .. ######).

    Returns a list of {"section": <heading text>, "text": <section text>}.
    Content before the first heading is kept under a synthetic "(preamble)".
    """
    lines = markdown_text.splitlines()
    sections: List[Dict[str, str]] = []
    current_heading = "(preamble)"
    current_lines: List[str] = []

    def flush() -> None:
        body = "\n".join(current_lines).strip()
        if body:
            sections.append({"section": current_heading, "text": body})

    for line in lines:
        stripped = line.lstrip()
        is_heading = stripped.startswith("#") and stripped.lstrip("#").startswith(" ")
        if is_heading:
            flush()
            current_heading = stripped.lstrip("#").strip()
            current_lines = [line]
        else:
            current_lines.append(line)
    flush()
    return sections


def _split_long_text(text: str) -> List[str]:
    """Split text that exceeds the token cap into overlapping token windows."""
    tokenizer = _get_tokenizer()
    token_ids = tokenizer.encode(text, add_special_tokens=False)
    if len(token_ids) <= MAX_TOKENS_PER_CHUNK:
        return [text]

    step = MAX_TOKENS_PER_CHUNK - OVERLAP_TOKENS
    if step <= 0:
        raise ValueError(
            "overlap_tokens must be smaller than max_tokens_per_chunk "
            f"(got overlap={OVERLAP_TOKENS}, max={MAX_TOKENS_PER_CHUNK})."
        )

    windows: List[str] = []
    start = 0
    while start < len(token_ids):
        window_ids = token_ids[start : start + MAX_TOKENS_PER_CHUNK]
        windows.append(tokenizer.decode(window_ids, skip_special_tokens=True).strip())
        if start + MAX_TOKENS_PER_CHUNK >= len(token_ids):
            break
        start += step
    return [w for w in windows if w]


def chunk(markdown_path: str) -> List[Dict[str, str]]:
    """Chunk a markdown file by heading/section, capped at the token limit.

    Sections longer than the cap are split into overlapping windows. Returns a
    list of {"chunk_id", "section", "text"} dicts. Pure: builds new objects.
    """
    path = Path(markdown_path)
    if not path.exists():
        raise FileNotFoundError(f"Markdown file not found: {markdown_path}")

    markdown_text = path.read_text(encoding="utf-8")
    sections = _split_into_sections(markdown_text)

    chunks: List[Dict[str, str]] = []
    for section in sections:
        for piece in _split_long_text(section["text"]):
            chunks.append(
                {
                    "chunk_id": str(len(chunks)),
                    "section": section["section"],
                    "text": piece,
                }
            )
    return chunks


# --- Step: per-chunk context (STUB) -----------------------------------------


def make_context(chunk_text: str, full_document_text: str, description: str) -> str:
    """Return a 1-2 sentence context string situating this chunk in the doc.

    STUB. The model that writes this context is decided later (out of scope for
    this setup). For now it returns a deterministic placeholder so the rest of
    the pipeline (embed, store, index, search) can be built and tested offline.
    Wire the chosen model in here later; keep the same in/out contract.
    """
    return f"[context placeholder] Section: {description}".strip()


# --- Step: embed + store + index --------------------------------------------


def _contextualize(context: str, text: str) -> str:
    """Prepend the chunk's context to its text (contextual-retrieval pattern)."""
    return f"{context}\n\n{text}".strip()


def _table_location(table_path: str) -> "tuple[str, str]":
    """Map a .../STEM.lance path to (db_uri, table_name) for LanceDB."""
    path = Path(table_path)
    db_uri = str(path.parent)
    table_name = path.name[: -len(".lance")] if path.name.endswith(".lance") else path.name
    if not table_name:
        raise ValueError(f"Could not derive a table name from {table_path}")
    return db_uri, table_name


def embed_and_store(chunks: List[Dict[str, str]], table_path: str) -> Dict[str, Any]:
    """Embed each chunk's contextualized text and write a LanceDB table.

    Builds the BM25 full-text index on the text column so hybrid search works.
    Each row has: chunk_id, section, context, text, contextualized_text, vector.
    Returns a small summary dict. Does not mutate the input chunks.
    """
    if not chunks:
        raise ValueError("No chunks to store.")

    import lancedb

    model = _get_model()

    rows: List[Dict[str, Any]] = []
    full_document_text = "\n\n".join(c["text"] for c in chunks)
    for c in chunks:
        context = make_context(c["text"], full_document_text, c["section"])
        contextualized_text = _contextualize(context, c["text"])
        vector = model.encode(contextualized_text, normalize_embeddings=True).tolist()
        if len(vector) != EMBEDDING_DIM:
            raise ValueError(
                f"Embedding dim {len(vector)} != configured {EMBEDDING_DIM}."
            )
        rows.append(
            {
                "chunk_id": c["chunk_id"],
                "section": c["section"],
                "context": context,
                "text": c["text"],
                "contextualized_text": contextualized_text,
                "vector": vector,
            }
        )

    db_uri, table_name = _table_location(table_path)
    Path(db_uri).mkdir(parents=True, exist_ok=True)
    db = lancedb.connect(db_uri)
    table = db.create_table(table_name, data=rows, mode="overwrite")

    # Native BM25 full-text index on the raw text column (no tantivy needed).
    table.create_fts_index("text", use_tantivy=False, replace=True)

    return {"table_path": table_path, "rows": len(rows), "table_name": table_name}


# --- Step: hybrid search ----------------------------------------------------

_RESULT_COLUMNS = ["chunk_id", "section", "context", "text", "contextualized_text"]


def search(query: str, table_path: str, k: int = 5) -> List[Dict[str, Any]]:
    """Hybrid (dense + BM25) search fused with Reciprocal Rank Fusion.

    Returns the top-k rows (vector column dropped for readability).
    """
    if not query or not query.strip():
        raise ValueError("Query must be a non-empty string.")

    import lancedb
    from lancedb.rerankers import RRFReranker

    db_uri, table_name = _table_location(table_path)
    db = lancedb.connect(db_uri)
    table = db.open_table(table_name)

    model = _get_model()
    query_vector = model.encode(query, normalize_embeddings=True).tolist()

    results = (
        table.search(query_type="hybrid")
        .vector(query_vector)
        .text(query)
        .rerank(RRFReranker())
        .select(_RESULT_COLUMNS)
        .limit(k)
        .to_list()
    )
    return results


# --- CLI --------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace) -> None:
    chunks = chunk(args.markdown_path)
    summary = embed_and_store(chunks, args.table_path)
    print(json.dumps({"chunks": len(chunks), **summary}, indent=2))


def _cmd_query(args: argparse.Namespace) -> None:
    rows = search(args.query, args.table_path, k=args.k)
    for i, row in enumerate(rows, start=1):
        print(f"--- result {i} | section: {row.get('section')} ---")
        print(row.get("text", "")[:500])
        print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Local contextual-retrieval backend.")
    sub = parser.add_subparsers(dest="command", required=True)

    build = sub.add_parser("build", help="Chunk a markdown file and build its table.")
    build.add_argument("markdown_path", help="Path to the source markdown file.")
    build.add_argument("table_path", help="Destination .lance table path.")
    build.set_defaults(func=_cmd_build)

    query = sub.add_parser("query", help="Hybrid-search a table.")
    query.add_argument("table_path", help="Path to the .lance table.")
    query.add_argument("query", help="The search query.")
    query.add_argument("--k", type=int, default=5, help="Number of results.")
    query.set_defaults(func=_cmd_query)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()

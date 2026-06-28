"""Local, persistent ChromaDB with on-CPU embeddings (no API key, free).

Uses Chroma's built-in DefaultEmbeddingFunction (all-MiniLM-L6-v2 via ONNX),
which downloads once on first use. Five collections per the spec.
"""
from __future__ import annotations

from functools import lru_cache

import chromadb
from chromadb.utils import embedding_functions

from app.config import settings

COLLECTIONS = (
    "resume_embeddings",
    "job_embeddings",
    "github_project_embeddings",
    "interest_embeddings",
    "cover_letter_embeddings",
)


@lru_cache(maxsize=1)
def _client() -> chromadb.api.ClientAPI:
    settings.ensure_dirs()
    return chromadb.PersistentClient(path=settings.chroma_path)


@lru_cache(maxsize=1)
def _embed_fn():
    # Local sentence-transformers all-MiniLM-L6-v2 (384-dim), runs on CPU.
    return embedding_functions.DefaultEmbeddingFunction()


def embed(texts: list[str]) -> list[list[float]]:
    """Embed text locally (no API). Returns one vector per input string."""
    return _embed_fn()(texts)


def cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if na == 0 or nb == 0:
        return 0.0
    return float(dot / (na * nb))  # cast off numpy float for JSON/DB serialization


def get_collection(name: str):
    if name not in COLLECTIONS:
        raise ValueError(f"Unknown collection {name!r}; expected one of {COLLECTIONS}")
    return _client().get_or_create_collection(name=name, embedding_function=_embed_fn())


def upsert(collection: str, *, id: str, document: str, metadata: dict | None = None) -> None:
    get_collection(collection).upsert(
        ids=[id], documents=[document], metadatas=[metadata or {}]
    )


def query(collection: str, *, text: str, n_results: int = 5) -> dict:
    return get_collection(collection).query(query_texts=[text], n_results=n_results)


def init_collections() -> None:
    for name in COLLECTIONS:
        get_collection(name)

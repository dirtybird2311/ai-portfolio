"""
News de-duplication with free Gemini embeddings.

"Acme beats estimates" and "Acme tops Q3 forecasts" are the same story; counting it twice would
double its weight in the news score. Each headline becomes an embedding (a list of numbers that
captures meaning); headlines whose meanings are nearly identical are merged, keeping the first.
If the embedding call fails, only exact-text duplicates are removed, as before.
"""
import numpy as np
import requests

from . import config

MODEL = "gemini-embedding-001"
SIMILAR = 0.88           # cosine similarity above this = same story


def embed(texts, post=None):
    key = config.secret("GEMINI_API_KEY", required=False)
    if not key or not texts:
        return None
    body = {"requests": [{"model": f"models/{MODEL}", "content": {"parts": [{"text": t}]}} for t in texts]}
    try:
        r = (post or requests.post)(f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:batchEmbedContents",
                 json=body, headers={"x-goog-api-key": key}, timeout=60)
        if r.status_code != 200:
            return None
        vecs = np.array([e["values"] for e in r.json()["embeddings"]], dtype=float)
        return vecs / np.maximum(np.linalg.norm(vecs, axis=1, keepdims=True), 1e-9)
    except Exception:
        return None


def dedupe(items, key="headline", post=None):
    """items: list of dicts with a headline. Returns (kept, merged_count)."""
    if len(items) < 2:
        return items, 0
    vecs = embed([i[key] for i in items], post)
    if vecs is None:
        return items, 0
    kept, kept_vecs = [], []
    for item, v in zip(items, vecs):
        if kept_vecs and max(float(v @ k) for k in kept_vecs) >= SIMILAR:
            continue
        kept.append(item)
        kept_vecs.append(v)
    return kept, len(items) - len(kept)

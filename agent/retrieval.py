"""Minimal embedding retriever for the full-context vs RAG comparison.

On a large corpus, dumping every rule and test into the prompt is slow and can
distract the model. RAG retrieves only the items most relevant to the in-scope
order domain. The embedding call is local (Ollama /api/embeddings); the ranking
is plain cosine top-k. `embed` is injectable so the ranking can be unit-tested
without a model.
"""
import math
import os

# The evaluation scope is always the three ORDER operations; retrieve toward it.
SCOPE_QUERY = ("주문 생성 조회 취소 업무 규칙: 수량 경계값 create_order, "
               "조회 소유권 get_order, 배송 후 취소 상태 cancel_order")


_CACHE = {}  # (model, text) -> embedding; the corpus is static, so embed each text once.


def ollama_embed(texts):
    import httpx
    url = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434").rstrip("/")
    model = os.getenv("EMBED_MODEL", os.getenv("OLLAMA_MODEL", "qwen3:8b"))
    out = []
    with httpx.Client(timeout=120) as client:
        for text in texts:
            key = (model, text)
            if key not in _CACHE:
                resp = client.post(url + "/api/embeddings", json={"model": model, "prompt": text})
                resp.raise_for_status()
                _CACHE[key] = resp.json()["embedding"]
            out.append(_CACHE[key])
    return out


def _cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


def top_k(query, items, k, embed=None):
    """items: list of (key, text). Return the keys of the k most similar to query,
    best first. k<=0 or k>=len returns all keys in original order."""
    keys = [key for key, _ in items]
    if k <= 0 or k >= len(items):
        return keys
    embed = embed or ollama_embed
    vectors = embed([query] + [text for _, text in items])
    qvec, rest = vectors[0], vectors[1:]
    ranked = sorted(((_cosine(qvec, v), key) for v, key in zip(rest, keys)),
                    key=lambda pair: pair[0], reverse=True)
    return [key for _, key in ranked[:k]]

"""Retrieval variants compared in step 4 (eval/compare_rag.py). The winner becomes the app default.

    python3 -m agents.retrievers        (run from app/, after agents.ingest; builds the section-aware index, ~3 min)

Two chunkings of the same cleaned sources:
  fixed    - the current ingest chunks (~900 chars, 150 overlap, sentence boundaries), read back from ChromaDB
  section  - paragraph-aware chunks (never cut mid-paragraph; a heading starts a new chunk) with a header line
             "report title | published | district | section" that is embedded and searched with the body
Retrieval pieces: dense (all-MiniLM-L6-v2, exact cosine), BM25 keyword, hybrid = reciprocal-rank fusion of the two,
metadata filter (time window of the cases + the store's Fed district), cross-encoder reranker (ms-marco-MiniLM-L-6-v2).
"""
from __future__ import annotations

import json
import math
import re
import time
from collections import Counter
from functools import lru_cache

import numpy as np

from .ingest import APP, COLLECTION, DISTRICTS, VSTORE, _SENT, clean, is_prose, registry, split_sections, ymd

INDEX = APP / "vectorstore" / "variants"
RERANKER = APP / "models" / "ms-marco-MiniLM-L-6-v2"
TARGET, HARD, MIN_FLUSH, HEAD_MAX = 800, 1100, 300, 100
POOL, RRF_K, RERANK_POOL = 50, 60, 30
STOP = set("the a an and or of in to for on at by with is was were are be been this that it as from its their our we "
           "what which how did does do during about said say".split())


def allowed_districts(fed_district: str | None) -> list[str]:
    """Cities named in the store's Fed-district field (some stores map to two or three possible districts)."""
    return [c for c in DISTRICTS if fed_district and re.search(rf"\b{re.escape(c)}\b", fed_district)]

VARIANTS = {
    "A":  dict(label="Fixed chunks, vector search (current core)", chunks="fixed", method="dense", filter=False, rerank=False),
    "A2": dict(label="A + time/district filter (current app)", chunks="fixed", method="dense", filter=True, rerank=False),
    "B":  dict(label="Fixed chunks, keyword search (BM25)", chunks="fixed", method="bm25", filter=False, rerank=False),
    "C":  dict(label="Fixed chunks, hybrid (vector + BM25)", chunks="fixed", method="hybrid", filter=False, rerank=False),
    "D":  dict(label="Section chunks + header, hybrid", chunks="section", method="hybrid", filter=False, rerank=False),
    "E":  dict(label="D + time/district filter", chunks="section", method="hybrid", filter=True, rerank=False),
    "F":  dict(label="E + cross-encoder reranker", chunks="section", method="hybrid", filter=True, rerank=True),
}


# ------------------------------------------------------------------------------------------ section-aware chunks
def _is_heading(p: str) -> bool:
    words = p.split()
    return (len(p) <= HEAD_MAX and len(words) >= 2 and p[0].isupper() and not p.rstrip().endswith((".", "?", "!", '"', ":", ";", ","))
            and sum(ch.isalpha() for ch in p) / len(p) > 0.7)


def _split_long(p: str) -> list[str]:
    out, cur = [], ""
    for s in _SENT.split(p):
        if cur and len(cur) + len(s) > TARGET:
            out.append(cur)
            cur = ""
        cur = f"{cur} {s}".strip()
    return out + [cur] if cur else out


def section_chunks(text: str) -> list[tuple[str, str]]:
    """(section heading, body) pieces of about TARGET characters, cut only between paragraphs."""
    out, cur, heading = [], [], ""

    def flush():
        if cur:
            out.append((heading, " ".join(cur)))
            cur.clear()

    for p in text.split("\n\n"):
        p = p.strip()
        if not p or p in {"—", "-", "•"}:
            continue
        if _is_heading(p):
            if sum(map(len, cur)) >= MIN_FLUSH:
                flush()
                heading = p
            else:
                cur.append(p)                        # short run so far: keep the heading inline
                heading = heading or p
            continue
        for piece in (_split_long(p) if len(p) > HARD else [p]):
            if cur and sum(len(x) + 1 for x in cur) + len(piece) > TARGET:
                flush()
            cur.append(piece)
    flush()
    return out


def _pretty(n: int) -> str:
    s = str(n)
    return f"{s[:4]}-{s[4:6]}-{s[6:]}"


def build_section_index() -> dict:
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    t0 = time.time()
    rows = []
    for doc in registry():
        for district, sec in split_sections(doc, clean(doc["file"].read_text(errors="ignore"))):
            for i, (head, body) in enumerate(section_chunks(sec)):
                if not is_prose(body):
                    continue
                meta = dict(doc_id=doc["id"], title=doc["title"], doc_type=doc["doc_type"], publisher=doc["publisher"],
                            evidence_type=doc["evidence_type"], district=district, section=head[:90], url=doc["url"],
                            published=ymd(doc["published"]), period_start=ymd(doc["start"]), period_end=ymd(doc["end"]),
                            source_file=str(doc["file"].relative_to(APP.parent / "sources")), chunk_index=i)
                where = "" if district == "National" else f" | {district} District"
                header = f"{doc['title']} | published {_pretty(meta['published'])}{where}" + (f" | {head[:90]}" if head else "")
                rows.append(dict(id=f"{doc['id']}::{district.replace(' ', '_')}::s{i}", text=body, header=header, meta=meta))
    ef = DefaultEmbeddingFunction()
    emb = np.vstack([np.array(ef([f"{r['header']}\n{r['text']}" for r in rows[i:i + 256]])) for i in range(0, len(rows), 256)])
    INDEX.mkdir(parents=True, exist_ok=True)
    (INDEX / "section_chunks.json").write_text(json.dumps(rows))
    np.save(INDEX / "section_emb.npy", emb.astype(np.float32))
    lens = [len(r["text"]) for r in rows]
    stats = dict(chunks=len(rows), avg_chars=round(np.mean(lens)), median_chars=int(np.median(lens)), seconds=round(time.time() - t0))
    (INDEX / "section_stats.json").write_text(json.dumps(stats))
    return stats


# ------------------------------------------------------------------------------------------ corpora
class Corpus:
    def __init__(self, rows: list[dict], emb: np.ndarray):
        self.rows = rows
        self.emb = emb / np.linalg.norm(emb, axis=1, keepdims=True)
        self.bm25 = BM25([f"{r.get('header', '')} {r['text']}" for r in rows])
        m = [r["meta"] for r in rows]
        self.start = np.array([x["period_start"] for x in m])
        self.end = np.array([x["period_end"] for x in m])
        self.pub = np.array([x["published"] for x in m])
        self.district = np.array([x["district"] for x in m])
        self.beige = np.array([x["doc_type"] == "beige_book" for x in m])

    def mask(self, ctx: dict | None) -> np.ndarray:
        """Time window: the report period overlaps the cases' window, or it was published inside it.
        Place: Beige Book chunks only for National + the store's district(s); Walmart reports always pass."""
        ok = np.ones(len(self.rows), bool)
        if not ctx:
            return ok
        s, e = ymd(ctx["start"]), ymd(ctx["end"])
        ok &= ((self.start <= e) & (self.end >= s)) | ((self.pub >= s) & (self.pub <= e))
        if ctx.get("districts"):
            ok &= ~self.beige | np.isin(self.district, ["National"] + list(ctx["districts"]))
        return ok


@lru_cache(maxsize=1)
def _ef():
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    return DefaultEmbeddingFunction()


@lru_cache(maxsize=2)
def corpus(name: str) -> Corpus:
    if name == "fixed":
        import chromadb
        got = chromadb.PersistentClient(path=str(VSTORE)).get_collection(COLLECTION).get(
            include=["documents", "metadatas", "embeddings"])
        rows = [dict(id=i, text=t, meta=m) for i, t, m in zip(got["ids"], got["documents"], got["metadatas"])]
        return Corpus(rows, np.array(got["embeddings"], dtype=np.float32))
    if not (INDEX / "section_chunks.json").exists():
        build_section_index()
    return Corpus(json.loads((INDEX / "section_chunks.json").read_text()), np.load(INDEX / "section_emb.npy"))


# ------------------------------------------------------------------------------------------ BM25
def tokens(text: str) -> list[str]:
    out = []
    for t in re.findall(r"[a-z0-9]+(?:\.[0-9]+)?", text.lower()):
        if t in STOP or len(t) < 2:
            continue
        out.append(t[:-1] if len(t) > 4 and t.endswith("s") and not t.endswith("ss") else t)   # light plural stemming
    return out


class BM25:
    def __init__(self, texts: list[str], k1: float = 1.5, b: float = 0.75):
        self.k1, self.b = k1, b
        self.tf = [Counter(tokens(t)) for t in texts]
        self.len = np.array([sum(c.values()) for c in self.tf], float)
        self.avg = self.len.mean()
        self.post: dict[str, list[int]] = {}
        for i, c in enumerate(self.tf):
            for t in c:
                self.post.setdefault(t, []).append(i)
        n = len(texts)
        self.idf = {t: math.log(1 + (n - len(p) + 0.5) / (len(p) + 0.5)) for t, p in self.post.items()}

    def scores(self, query: str) -> np.ndarray:
        s = np.zeros(len(self.tf))
        for t in set(tokens(query)):
            for i in self.post.get(t, []):
                f = self.tf[i][t]
                s[i] += self.idf[t] * f * (self.k1 + 1) / (f + self.k1 * (1 - self.b + self.b * self.len[i] / self.avg))
        return s


# ------------------------------------------------------------------------------------------ reranker
@lru_cache(maxsize=1)
def _cross_encoder():
    import onnxruntime as ort
    from tokenizers import Tokenizer
    tok = Tokenizer.from_file(str(RERANKER / "tokenizer.json"))
    tok.enable_truncation(512)
    tok.enable_padding()
    return tok, ort.InferenceSession(str(RERANKER / "model_quantized.onnx"), providers=["CPUExecutionProvider"])


def rerank_scores(query: str, passages: list[str]) -> np.ndarray:
    tok, sess = _cross_encoder()
    enc = tok.encode_batch([(query, p) for p in passages])
    feed = dict(input_ids=np.array([e.ids for e in enc], np.int64), attention_mask=np.array([e.attention_mask for e in enc], np.int64),
                token_type_ids=np.array([e.type_ids for e in enc], np.int64))
    names = {i.name for i in sess.get_inputs()}
    return sess.run(None, {k: v for k, v in feed.items() if k in names})[0][:, 0]


# ------------------------------------------------------------------------------------------ search
def _top(scores: np.ndarray, ok: np.ndarray, n: int) -> list[int]:
    s = np.where(ok, scores, -np.inf)
    idx = np.argpartition(-s, min(n, len(s) - 1))[:n]
    return [int(i) for i in idx[np.argsort(-s[idx])] if np.isfinite(s[i])]


def search(query: str, variant: str = "F", k: int = 10, ctx: dict | None = None) -> list[dict]:
    """Top-k chunks for one query. ctx = {start, end, districts} is used only by the filtered variants."""
    v = VARIANTS[variant]
    c = corpus(v["chunks"])
    ok = c.mask(ctx if v["filter"] else None)
    pool = RERANK_POOL if v["rerank"] else k
    if v["method"] in ("dense", "hybrid"):
        q = np.array(_ef()([query]))[0]
        dense = _top(c.emb @ (q / np.linalg.norm(q)), ok, POOL)
    if v["method"] in ("bm25", "hybrid"):
        kw = _top(c.bm25.scores(query), ok, POOL)
    if v["method"] == "dense":
        ranked = dense
    elif v["method"] == "bm25":
        ranked = kw
    else:                                                          # reciprocal-rank fusion
        rrf: dict[int, float] = {}
        for lst in (dense, kw):
            for r, i in enumerate(lst):
                rrf[i] = rrf.get(i, 0) + 1 / (RRF_K + r + 1)
        ranked = sorted(rrf, key=rrf.get, reverse=True)
    ranked = ranked[:pool]
    if v["rerank"] and ranked:
        ce = rerank_scores(query, [f"{c.rows[i].get('header', '')}\n{c.rows[i]['text']}" for i in ranked])
        ranked = [ranked[j] for j in np.argsort(-ce)]
    return [dict(c.rows[i], rank=r + 1) for r, i in enumerate(ranked[:k])]


if __name__ == "__main__":
    print(json.dumps(build_section_index(), indent=1))

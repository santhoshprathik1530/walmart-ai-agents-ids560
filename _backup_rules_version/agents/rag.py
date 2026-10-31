"""RAG Agent: finds report passages that were published in the right time and place, then ranks them.

Retrieval strategy (every step is measured and returned in `stats` for the deck and the live trace):
  1. Query plan    1-4 short natural-language queries from the payload and the evidence (category, consumer demand,
                   calendar event, fuel / weather signal), instead of one long keyword string.
  2. Metadata filter, applied inside ChromaDB BEFORE the vector search:
                   time   = report period covers the week, OR published in the 3 weeks before it, OR its period just ended
                   place  = the store's Fed district(s) or national
  3. Vector search  top 25 chunks per query, cosine similarity (all-MiniLM-L6-v2 embeddings), results merged across queries
  4. Re-rank       chunk similarity + best-sentence similarity + keyword overlap + same-district / period-covers-week boosts
  5. Select        top k, at most 2 chunks per report; always keep the best Walmart chunk and the best local-district chunk
  6. Quote         the best-matching sentence of each chunk is kept as a verbatim quote (sentence-level scores also feed step 4)
"""
from __future__ import annotations

import re
import time
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from .engine import UNIT_TERMS
from .ingest import COLLECTION, DISTRICTS, ORDINAL, VSTORE, _SENT, ymd

TOP_PER_QUERY, K_DEFAULT, MAX_PER_DOC, GRACE_DAYS = 25, 6, 2, 21
STOP = set("the a an and or of in to for on at by with is was were are be been this that it as from its their our we".split())


def _suffix(n: int) -> str:
    return "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")


def district_label(city: str) -> str:
    if city == "National":
        return "National"
    n = DISTRICTS.index(city) + 1
    return f"{city} Fed ({n}{_suffix(n)} District)"


def allowed_districts(fed_district: str | None) -> list[str]:
    """Cities named in the store's Fed-district field (some stores map to two or three possible districts)."""
    names = [c for c in DISTRICTS if fed_district and re.search(rf"\b{re.escape(c)}\b", fed_district)]
    return names


@lru_cache(maxsize=1)
def _store():
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction
    ef = DefaultEmbeddingFunction()
    col = chromadb.PersistentClient(path=str(VSTORE)).get_collection(COLLECTION, embedding_function=ef)
    return col, ef


def season_phrase(w: pd.Timestamp) -> str:
    return {1: "holiday season Christmas New Year", 2: "Super Bowl Valentine's Day winter weather", 3: "Easter spring season",
            4: "Easter spring season", 5: "Mother's Day spring", 6: "summer season", 7: "back-to-school summer",
            8: "back-to-school", 9: "back-to-school fall", 10: "Halloween fall season", 11: "Black Friday holiday season",
            12: "holiday season Christmas"}[w.month]


def build_queries(pl: dict, ev: dict) -> list[dict]:
    """Short natural-language queries describing what the analyst needs explained."""
    w = pd.Timestamp(pl["week_ending"])
    season = season_phrase(w)
    if pl.get("grain") == "store_week":
        depts = [x["dept_name"].split(" (")[0].lower() for x in pl["top_depts"][:4]]
        cat = f"{', '.join(depts)} sales and comp sales trend"
        cat2 = " ".join(sorted({UNIT_TERMS[u][0] for u in pl["units"] if u in UNIT_TERMS}))
        qs = [dict(name="category", text=f"{cat}; {cat2} business"),
              dict(name="demand", text=f"retail sales and consumer spending, {season}")]
    else:
        unit = pl["merch_unit"]
        extra = " ".join(UNIT_TERMS.get(unit, [])[:3])
        qs = [dict(name="category", text=f"{pl['dept_name'].lower()} sales and comp trend, {unit.lower()} business, {extra}"),
              dict(name="demand", text=f"retail sales and consumer spending, {season}")]
    flags = " ".join(ev.get("calendar_flags", []))
    if "Easter" in flags:
        qs.append(dict(name="event", text="Easter timing and holiday sales shift"))
    elif "Christmas" in flags or "Post-holiday" in flags:
        qs.append(dict(name="event", text="holiday season sales, Christmas and into the New Year, fourth quarter seasonality"))
    fuel, fly = ev.get("fuel"), ev.get("fuel_ly")
    if fly == fly and fly and abs(fuel / fly - 1) > 0.08:
        qs.append(dict(name="fuel", text="gasoline prices and consumer spending"))
    t, tly = ev.get("temp"), ev.get("temp_ly")
    if tly == tly and tly and abs(t - tly) > 8:
        qs.append(dict(name="weather", text="unusual weather effect on retail sales"))
    return qs


def build_filter(w: pd.Timestamp, cities: list[str]) -> dict:
    d, g = ymd(w), ymd(w - pd.Timedelta(days=GRACE_DAYS))
    time_rule = {"$or": [
        {"$and": [{"period_start": {"$lte": d}}, {"period_end": {"$gte": d}}]},          # report period covers the week
        {"$and": [{"published": {"$gte": g}}, {"published": {"$lte": d}}]},               # published in the 3 weeks before
        {"$and": [{"period_end": {"$gte": g}}, {"period_end": {"$lte": d}}]},             # period ended just before
    ]}
    return {"$and": [time_rule, {"district": {"$in": ["National"] + cities}}]}


def _relation(meta: dict, d: int, g: int) -> str:
    if meta["period_start"] <= d <= meta["period_end"]:
        return "covers the week"
    if g <= meta["published"] <= d:
        return "published just before"
    return "period just ended"


def _terms(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z][a-z\-]+", text.lower()) if t not in STOP and len(t) > 2}


def retrieve(pl: dict, ev: dict, k: int = K_DEFAULT, queries: list[dict] | None = None) -> dict:
    t0 = time.time()
    col, ef = _store()
    w = pd.Timestamp(pl["week_ending"])
    cities = allowed_districts(pl.get("fed_district"))
    where = build_filter(w, cities)
    queries = [dict(q) for q in (queries or build_queries(pl, ev))]
    d, g = ymd(w), ymd(w - pd.Timedelta(days=GRACE_DAYS))

    total = col.count()
    ids_ok = col.get(where=where, include=["metadatas"])
    n_filtered, n_docs = len(ids_ok["ids"]), len({m["doc_id"] for m in ids_ok["metadatas"]})

    cand: dict[str, dict] = {}
    for q in queries:
        tq = time.time()
        r = col.query(query_texts=[q["text"]], n_results=TOP_PER_QUERY, where=where, include=["documents", "metadatas", "distances"])
        q["ms"] = round((time.time() - tq) * 1000)
        q["hits"] = len(r["ids"][0])
        for cid, doc, meta, dist in zip(r["ids"][0], r["documents"][0], r["metadatas"][0], r["distances"][0]):
            c = cand.setdefault(cid, dict(chunk_id=cid, text=doc, meta=meta, sim=0.0, queries=[]))
            c["sim"] = max(c["sim"], 1 - dist)
            c["queries"].append(q["name"])

    qterms = set().union(*(_terms(q["text"]) for q in queries)) if queries else set()
    qvecs = np.array(ef([q["text"] for q in queries])) if queries else np.zeros((1, 384))
    qvecs /= np.linalg.norm(qvecs, axis=1, keepdims=True)

    # sentence-level re-rank of the 30 best chunks: embed every sentence once, keep each chunk's best-matching sentence
    pre = sorted(cand.values(), key=lambda c: c["sim"], reverse=True)[:30]
    def sents_of(text):
        ss = [s.strip().strip('"') for s in _SENT.split(text) if len(s.strip()) > 25]
        short = [s for s in ss if len(s) <= 260]          # keep quotes short enough to put on a slide
        return short or ss or [text.strip()]

    sents = [sents_of(c["text"]) for c in pre]
    flat = [s for ss in sents for s in ss]
    vecs = np.array(ef(flat))
    vecs /= np.linalg.norm(vecs, axis=1, keepdims=True)
    sims, i = vecs @ qvecs.T, 0
    for c, ss in zip(pre, sents):
        block = sims[i:i + len(ss)]
        i += len(ss)
        j = int(block.max(axis=1).argmax())
        c["quote"], c["sent_sim"] = ss[j], float(block[j].max())
    for c in cand.values():
        m = c["meta"]
        c["local"] = m["district"] in cities
        c["relation"] = _relation(m, d, g)
        c.setdefault("sent_sim", c["sim"] - 0.1)
        kw = len(qterms & _terms(c["text"])) / max(len(qterms), 1)
        c["score"] = 0.45 * c["sim"] + 0.55 * c["sent_sim"] + 0.25 * kw + (0.06 if c["local"] else 0) \
            + (0.04 if c["relation"] == "covers the week" else 0) + 0.02 * (len(c["queries"]) - 1)
    ranked = sorted((c for c in cand.values() if "quote" in c), key=lambda c: c["score"], reverse=True)

    chosen: list[dict] = []

    def take(c):
        if c and c not in chosen and sum(x["meta"]["doc_id"] == c["meta"]["doc_id"] for x in chosen) < MAX_PER_DOC:
            chosen.append(c)

    take(next((c for c in ranked if c["meta"]["evidence_type"].startswith("Walmart")), None))
    take(next((c for c in ranked if c["local"] and c["meta"]["doc_type"] == "beige_book"), None))
    for c in ranked:
        if len(chosen) >= k:
            break
        take(c)
    chosen.sort(key=lambda c: c["score"], reverse=True)

    passages = []
    for c in chosen:
        m = c["meta"]
        passages.append(dict(
            text=c["text"], quote=c["quote"], doc=m["title"], doc_id=m["doc_id"],
            published=f"{str(m['published'])[:4]}-{str(m['published'])[4:6]}-{str(m['published'])[6:]}", url=m["url"],
            evidence_type=m["evidence_type"], district=district_label(m["district"]), publisher=m["publisher"],
            score=round(c["score"], 3), sim=round(c["sim"], 3), relation=c["relation"], chunk_id=c["chunk_id"],
            source_file=m["source_file"], section=m["section"], queries=sorted(set(c["queries"])), doc_type=m["doc_type"]))
    stats = dict(chunks_in_store=total, chunks_after_filter=n_filtered, reports_after_filter=n_docs, queries=len(queries),
                 candidates=len(cand), returned=len(passages), districts=["National"] + cities, ms=round((time.time() - t0) * 1000),
                 reports_in_store=_n_reports())
    return dict(queries=queries, passages=passages, stats=stats, filter=where)


@lru_cache(maxsize=1)
def _n_reports() -> int:
    col, _ = _store()
    return len({m["doc_id"] for m in col.get(include=["metadatas"])["metadatas"]})

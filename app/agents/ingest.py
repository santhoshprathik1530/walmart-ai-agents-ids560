"""Build the RAG vector store from the original source files in sources/.

    python3 -m agents.ingest            (run from app/)

Pipeline: read each original report -> clean the text -> split Beige Books by Fed district -> cut into overlapping
~900-character chunks at sentence boundaries -> drop table/number noise -> embed (all-MiniLM-L6-v2, ONNX, 384-dim)
-> store in a persistent ChromaDB collection with metadata (publisher, evidence type, district, period, published date).
Writes vectorstore/stats.json with the numbers shown on the deck.
"""
from __future__ import annotations

import csv
import json
import re
import shutil
import time
from datetime import date, datetime
from pathlib import Path

import pandas as pd

APP = Path(__file__).resolve().parent.parent
ROOT = APP.parent
SOURCES = ROOT / "sources"
VSTORE = APP / "vectorstore"
COLLECTION = "walmart_reports"
EMBED_MODEL = "all-MiniLM-L6-v2 (ONNX, 384-dim)"

CHUNK_CHARS, OVERLAP_CHARS, MIN_CHARS = 900, 150, 200
DISTRICTS = ["Boston", "New York", "Philadelphia", "Cleveland", "Richmond", "Atlanta", "Chicago", "St. Louis",
             "Minneapolis", "Kansas City", "Dallas", "San Francisco"]
ORDINAL = ["First", "Second", "Third", "Fourth", "Fifth", "Sixth", "Seventh", "Eighth", "Ninth", "Tenth", "Eleventh", "Twelfth"]
WALMART, REGIONAL = "Walmart-level context", "Regional / macro context"


def ymd(d) -> int:
    return int(pd.Timestamp(d).strftime("%Y%m%d"))


# ------------------------------------------------------------------------------------------ document registry
def _manifest() -> dict:
    with open(SOURCES / "MANIFEST.csv") as f:
        return {r["local_file"]: r for r in csv.DictReader(f)}


def _quarters(cal: pd.DataFrame) -> dict:
    out = {}
    for per, g in cal.groupby("Fiscal Period"):
        fy, q = per.split()
        out[f"FY{fy[4:]}{q}"] = (g["Week Starts (Sat)"].min(), g["Quarter Ends"].max())
    return out


def registry() -> list[dict]:
    """Every source file that goes into the vector store, with the metadata every chunk inherits."""
    cal = pd.read_csv(APP / "data" / "fiscal_calendar.csv", parse_dates=["Week Starts (Sat)", "Quarter Ends"])
    quarters, man = _quarters(cal), _manifest()
    docs, release_date = [], {}

    def url(path: Path) -> str:
        ext = next((x for x in (".htm", ".html", ".pdf") if path.with_suffix(x).exists()), ".pdf")
        key = str(path.relative_to(SOURCES).with_suffix(ext))
        return man.get(key, {}).get("source_url", "")

    for f in sorted((SOURCES / "walmart" / "earnings_releases").glob("*.txt")):
        q = re.search(r"WMT_(FY\d\dQ\d)_", f.name).group(1)
        pub = re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1)
        release_date[q] = pub
        s, e = quarters[q]
        docs.append(dict(id=f"WMT-{q}-RELEASE", title=f"Walmart {q[:4]} {q[4:]} earnings release", file=f, doc_type="earnings_release",
                         publisher="Walmart", evidence_type=WALMART, published=pub, start=s, end=e, url=url(f), kind="plain"))
    for f in sorted((SOURCES / "walmart" / "earnings_calls").glob("*.txt")):
        q = re.search(r"WMT_(FY\d\dQ\d)_", f.name).group(1)
        s, e = quarters[q]
        docs.append(dict(id=f"WMT-{q}-CALL", title=f"Walmart {q[:4]} {q[4:]} earnings call transcript", file=f, doc_type="earnings_call",
                         publisher="Walmart Investor Relations", evidence_type=WALMART, published=release_date[q], start=s, end=e,
                         url=url(f), kind="plain"))
    for f in sorted((SOURCES / "walmart" / "10k").glob("*.txt")):
        fy = int(re.search(r"FY(\d{4})", f.name).group(1))
        ar = "annual_report" in f.name
        pub = {2010: "2010-03-30", 2011: "2011-03-30", 2012: "2012-03-27", 2013: "2013-03-26"}[fy]
        docs.append(dict(id=f"WMT-{'AR' if ar else '10K'}-FY{fy}", title=f"Walmart FY{fy} {'annual report (MD&A)' if ar else '10-K'}", file=f,
                         doc_type="annual_report" if ar else "10k", publisher="Walmart (SEC)", evidence_type=WALMART, published=pub,
                         start=date(fy - 1, 2, 1), end=date(fy, 1, 31), url=url(f), kind="plain"))
    for f in sorted((SOURCES / "walmart" / "other_ir").glob("*comp_sales*.txt")):
        q = re.search(r"WMT_(FY\d\dQ\d)_", f.name).group(1)
        s, e = quarters[q]
        docs.append(dict(id=f"WMT-{q}-COMPS", title=f"Walmart {q[:4]} {q[4:]} 13-week comparable sales disclosure", file=f, doc_type="comp_sales",
                         publisher="Walmart Investor Relations", evidence_type=WALMART, published=release_date.get(q, str(e.date())),
                         start=s, end=e, url=url(f), kind="plain"))
    filed_10q = {"FY13Q1": "2012-06-01", "FY13Q2": "2012-09-06", "FY13Q3": "2012-12-04"}
    for f in sorted((SOURCES / "walmart" / "10q").glob("*.txt")):
        q = re.search(r"WMT_(FY\d\dQ\d)_", f.name).group(1)
        s, e = quarters[q]
        docs.append(dict(id=f"WMT-{q}-10Q", title=f"Walmart {q[:4]} {q[4:]} 10-Q", file=f, doc_type="10q",
                         publisher="Walmart (SEC)", evidence_type=WALMART, published=filed_10q[q], start=s, end=e,
                         url=url(f), kind="plain"))
    for f in sorted((SOURCES / "walmart" / "newsroom").glob("*.txt")):
        pub = re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1)
        slug = f.stem.split(pub + "_")[1]
        docs.append(dict(id=f"WMT-NEWS-{pub}-{slug}", title=f"Walmart news release, {pub}: {f.read_text().splitlines()[0][:90]}",
                         file=f, doc_type="news_release", publisher="Walmart", evidence_type=WALMART, published=pub,
                         start=pd.Timestamp(pub), end=pd.Timestamp(pub) + pd.Timedelta(weeks=8), url=url(f),
                         kind="plain"))   # a release is relevant for the ~8 weeks after it is issued
    beige = sorted((SOURCES / "fed_beige_book").glob("*.txt"))
    dates = [datetime.strptime(re.search(r"(\d{4}-\d{2}-\d{2})", f.name).group(1), "%Y-%m-%d").date() for f in beige]
    for i, (f, d) in enumerate(zip(beige, dates)):
        prev = dates[i - 1] if i else date(2009, 12, 2)
        docs.append(dict(id=f"BB-{d:%Y-%m-%d}", title=f"Federal Reserve Beige Book, {d:%b %d, %Y}", file=f, doc_type="beige_book",
                         publisher="Federal Reserve", evidence_type=REGIONAL, published=str(d), start=prev + pd.Timedelta(days=1), end=d,
                         url=url(f), kind="beige"))
    for f in sorted((SOURCES / "nrf").glob("*.txt")):
        d = re.search(r"(\d{4})-(\d{2})-(\d{2})", f.name)
        y = int(d.group(1))
        docs.append(dict(id=f"NRF-{y}-HOLIDAY", title=f"NRF {y} holiday sales forecast", file=f, doc_type="nrf_forecast",
                         publisher="National Retail Federation", evidence_type=REGIONAL, published=d.group(0), start=date(y, 11, 1),
                         end=date(y, 12, 31), url=url(f).replace(".htm", ".html"), kind="nrf"))
    return docs


# ------------------------------------------------------------------------------------------ text -> chunks
def clean(text: str) -> str:
    text = text.replace("\r", "\n").replace("’", "'").replace("‟", "'").replace("“", '"').replace("”", '"')
    text = re.sub(r"(?m)^\s*\d{1,3}\s*$", "", text)                      # bare page numbers
    text = re.sub(r"(?im)^\s*(table of contents|return to top)\s*$", "", text)
    text = re.sub(r"[ \t\xa0]+", " ", text)
    paras = [re.sub(r"\s*\n\s*", " ", p).strip() for p in re.split(r"\n\s*\n", text)]
    return "\n\n".join(p for p in paras if p)


def split_sections(doc: dict, text: str) -> list[tuple[str, str]]:
    """(district, text). Beige Books are split by Fed district so every chunk knows which district it describes."""
    if doc["kind"] == "nrf":
        a = text.find("Washington,")
        b = text.find("###")
        return [("National", text[a:b if b > a else None])]
    if doc["kind"] != "beige":
        return [("National", text)]
    marks = []
    for i, city in enumerate(DISTRICTS):
        m = re.search(rf"{ORDINAL[i]} District\s*[-–—]+\s*{re.escape(city)}", text)
        if m:
            marks.append((m.start(), m.end(), city))
    marks.sort()
    if not marks:
        return [("National", text)]
    out = [("National", text[:marks[0][0]])]
    for k, (s, e, city) in enumerate(marks):
        end = marks[k + 1][0] if k + 1 < len(marks) else len(text)
        out.append((city, text[e:end]))
    return out


_SENT = re.compile(r"(?<=[.!?])\s+(?=[A-Z\"'(••])")


def sentences(par: str) -> list[str]:
    return [s.strip() for s in _SENT.split(par) if s.strip()]


def chunk(text: str) -> list[str]:
    """Overlapping chunks of about CHUNK_CHARS characters, cut at sentence boundaries."""
    sents = [s for p in text.split("\n\n") for s in sentences(p)]
    chunks, cur = [], []
    for s in sents:
        if cur and sum(len(x) + 1 for x in cur) + len(s) > CHUNK_CHARS:
            chunks.append(" ".join(cur))
            tail, n = [], 0
            for x in reversed(cur):                 # carry the last sentences over as overlap
                if n + len(x) > OVERLAP_CHARS:
                    break
                tail.insert(0, x)
                n += len(x) + 1
            cur = tail
        cur.append(s)
    if cur:
        chunks.append(" ".join(cur))
    if len(chunks) > 1 and len(chunks[-1]) < MIN_CHARS:      # fold a tiny tail into the previous chunk
        chunks[-2] += " " + chunks.pop()
    return chunks


def is_prose(c: str) -> bool:
    """Drop chunks that are mostly numbers or table fragments."""
    letters = sum(ch.isalpha() for ch in c)
    digits = sum(ch.isdigit() for ch in c)
    return len(c) >= MIN_CHARS // 2 and letters / len(c) >= 0.62 and digits / len(c) <= 0.12


# ------------------------------------------------------------------------------------------ build
def build(rebuild: bool = True) -> dict:
    import chromadb
    from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

    t0 = time.time()
    if rebuild and VSTORE.exists():
        shutil.rmtree(VSTORE)
    client = chromadb.PersistentClient(path=str(VSTORE))
    col = client.get_or_create_collection(COLLECTION, embedding_function=DefaultEmbeddingFunction(),
                                          metadata={"hnsw:space": "cosine"})
    ids, texts, metas = [], [], []
    per_type: dict = {}
    dropped = total_raw = 0
    docs = registry()
    for doc in docs:
        raw = clean((doc["file"]).read_text(errors="ignore"))
        n_before = 0
        for district, sec in split_sections(doc, raw):
            for i, c in enumerate(chunk(sec)):
                n_before += 1
                if not is_prose(c):
                    dropped += 1
                    continue
                ids.append(f"{doc['id']}::{district.replace(' ', '_')}::{i}")
                texts.append(c)
                metas.append(dict(doc_id=doc["id"], title=doc["title"], doc_type=doc["doc_type"], publisher=doc["publisher"],
                                  evidence_type=doc["evidence_type"], district=district, section=district, url=doc["url"],
                                  published=ymd(doc["published"]), period_start=ymd(doc["start"]), period_end=ymd(doc["end"]),
                                  source_file=str(doc["file"].relative_to(SOURCES)), chunk_index=i))
        total_raw += n_before
        pt = per_type.setdefault(doc["doc_type"], dict(files=0, chunks=0, chars=0))
        pt["files"] += 1
    for m, t in zip(metas, texts):
        pt = per_type[m["doc_type"]]
        pt["chunks"] += 1
        pt["chars"] += len(t)
    for i in range(0, len(ids), 256):                           # embed + store in batches
        col.add(ids=ids[i:i + 256], documents=texts[i:i + 256], metadatas=metas[i:i + 256])
    size = sum(p.stat().st_size for p in VSTORE.rglob("*") if p.is_file())
    words = sum(len(t.split()) for t in texts)
    stats = dict(
        files=len(docs), chunks=len(ids), chunks_before_quality_filter=total_raw, dropped_noise_chunks=dropped,
        avg_chunk_chars=round(sum(map(len, texts)) / len(texts)), avg_chunk_words=round(words / len(texts)),
        approx_tokens=round(words * 1.3), chunk_target_chars=CHUNK_CHARS, overlap_chars=OVERLAP_CHARS,
        embedding_model=EMBED_MODEL, embedding_dim=384, index="HNSW, cosine distance", collection=COLLECTION,
        vector_store_bytes=size, vector_store_mb=round(size / 1e6, 1), build_seconds=round(time.time() - t0, 1),
        per_type={k: dict(files=v["files"], chunks=v["chunks"], avg_chars=round(v["chars"] / v["chunks"]) if v["chunks"] else 0)
                  for k, v in sorted(per_type.items())},
        beige_districts=sorted({m["district"] for m in metas if m["doc_type"] == "beige_book"}),
    )
    (VSTORE / "stats.json").write_text(json.dumps(stats, indent=1))
    return stats


if __name__ == "__main__":
    s = build()
    print(json.dumps(s, indent=1))

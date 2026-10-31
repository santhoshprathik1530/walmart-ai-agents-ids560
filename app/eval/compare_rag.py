"""Step 4: compare the retrieval variants (agents/retrievers.py) on the golden report questions.

    python3 -m eval.compare_rag                 retrieval only (free, ~1 min)
    python3 -m eval.compare_rag --answers A E F  also answer + grade with the LLM for those variants (cached, ~$0.05 each)

Retrieval: a chunk is a hit if it holds the item's evidence quote (word for word, or at least 60% of it as one unbroken
piece, so a quote cut by a chunk border still counts). Metrics per variant: Hit@1, Hit@5, MRR@10, all quotes in top 5,
characters of context in the top 5, ms per query, with 95% bootstrap intervals for Hit@5 and MRR.
Answers: the LLM answers from the top 5 chunks only; a second LLM call grades it against the reference answer
(correct 1 / 0.5 / 0) and checks every claim against the chunks (faithful 1 / 0). Unanswerable items are correct only
if the answer says the sources do not contain it.
Writes eval/results/rag_items.csv, rag_comparison.csv, rag_comparison.json, rag_answers_<variant>.json.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np
import pandas as pd

from agents import llm
from agents.retrievers import VARIANTS, corpus, search

EVAL = Path(__file__).resolve().parent
OUT = EVAL / "results"
WINDOW = dict(start="2012-06-29", end="2012-10-26")      # v3.3 case weeks (Jul 20 - Oct 26, 2012) plus 3 weeks before
COVER, K, JUDGE_MODEL = 0.6, 10, ["anthropic/claude-haiku-5.5"]


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.replace("’", "'").replace("“", '"').replace("”", '"')).strip().lower()


def covers(quote: str, text: str) -> bool:
    q, t = norm(quote), norm(text)
    if q in t:
        return True
    m = SequenceMatcher(None, q, t, autojunk=False).find_longest_match(0, len(q), 0, len(t))
    return m.size >= COVER * len(q)


def items() -> list[dict]:
    return [g for g in json.loads((EVAL / "golden_qa.json").read_text()) if g["type"] == "report"]


def context(it: dict) -> dict:
    d = it["tags"].get("district")
    return dict(WINDOW, districts=[d] if d and d != "National" else [])


def gold_ids(chunks: str, it: dict) -> list[set[str]]:
    """For each evidence quote, the chunk ids (in this chunking) that hold it."""
    c = corpus(chunks)
    out = []
    for ev in it["evidence"]:
        out.append({r["id"] for r in c.rows if r["meta"]["doc_id"] == ev["doc_id"] and covers(ev["quote"], r["text"])})
    return out


def boot(x: np.ndarray, n: int = 2000, seed: int = 7) -> tuple[float, float]:
    rng = np.random.default_rng(seed)
    m = x[rng.integers(0, len(x), (n, len(x)))].mean(axis=1)
    return float(np.percentile(m, 2.5)), float(np.percentile(m, 97.5))


# ------------------------------------------------------------------------------------------ retrieval
def run_retrieval(variants: list[str]) -> tuple[pd.DataFrame, dict]:
    rows, hits = [], {}
    golds = {}
    for v in variants:
        for it in items():
            if it.get("unanswerable"):
                continue
            ch = VARIANTS[v]["chunks"]
            if (ch, it["id"]) not in golds:
                golds[ch, it["id"]] = gold_ids(ch, it)
            gold = golds[ch, it["id"]]
            t = time.time()
            res = search(it["question"], v, K, context(it))
            ms = (time.time() - t) * 1000
            ids = [r["id"] for r in res]
            any_gold = set().union(*gold)
            first = next((r["rank"] for r in res if r["id"] in any_gold), None)
            hits[v, it["id"]] = res
            rows.append(dict(variant=v, id=it["id"], question=it["question"], gold_chunks=len(any_gold), first_hit_rank=first,
                             hit1=int(first == 1), hit5=int(bool(first and first <= 5)), rr=1 / first if first else 0.0,
                             all_quotes5=int(all(g & set(ids[:5]) for g in gold)),
                             ctx_chars5=sum(len(r["text"]) for r in res[:5]), ms=round(ms, 1),
                             top1=f"{res[0]['meta']['doc_id']} | {res[0]['text'][:90]}" if res else ""))
    return pd.DataFrame(rows), hits


def summarise(df: pd.DataFrame) -> pd.DataFrame:
    out = []
    for v, g in df.groupby("variant", sort=False):
        h5, rr = g.hit5.to_numpy(float), g.rr.to_numpy(float)
        out.append(dict(variant=v, label=VARIANTS[v]["label"], n=len(g), hit1=g.hit1.mean(), hit5=h5.mean(),
                        hit5_ci=boot(h5), mrr=rr.mean(), mrr_ci=boot(rr), all_quotes5=g.all_quotes5.mean(),
                        ctx_chars5=round(g.ctx_chars5.mean()), ms=round(g.ms.median(), 1),
                        chunks=len(corpus(VARIANTS[v]["chunks"]).rows), missing_gold=int((g.gold_chunks == 0).sum())))
    return pd.DataFrame(out)


# ------------------------------------------------------------------------------------------ answers
ANSWER_SYS = ("You answer questions about Walmart and Federal Reserve reports from 2012. Use ONLY the passages given. "
              "Answer in one or two sentences with the exact figures from the passages. If the passages do not contain the "
              "answer, reply exactly: Not in the sources.")
JUDGE_SYS = ("You grade a RAG system. Reply with JSON only: {\"correct\": 1 or 0.5 or 0, \"faithful\": 1 or 0, \"why\": \"at most 20 words\"}. "
             "correct: 1 if the candidate gives the reference answer's key facts (same figures), 0.5 if partly, 0 if wrong or it "
             "declines. For an UNANSWERABLE question, correct is 1 only if the candidate says the sources do not contain it. "
             "faithful: 1 if every claim in the candidate is supported by the passages (a refusal counts as faithful), else 0.")


def _passages(res: list[dict]) -> str:
    return "\n\n".join(f"[{i + 1}] {r['meta']['title']} (published {str(r['meta']['published'])[:4]}-"
                       f"{str(r['meta']['published'])[4:6]}-{str(r['meta']['published'])[6:]}"
                       f"{'' if r['meta']['district'] == 'National' else ', ' + r['meta']['district'] + ' District'})\n{r['text']}"
                       for i, r in enumerate(res[:5]))


def run_answers(v: str) -> pd.DataFrame:
    path = OUT / f"rag_answers_{v}.json"
    cache = json.loads(path.read_text()) if path.exists() else {}
    for it in items():
        if cache.get(it["id"], {}).get("correct") is not None:        # graded already; failed ones are retried
            continue
        res = search(it["question"], v, 5, context(it))
        ctx = _passages(res)
        a = llm.complete(ANSWER_SYS, f"Passages:\n{ctx}\n\nQuestion: {it['question']}", 500, models=JUDGE_MODEL)
        if not a:
            print(f"  {v} {it['id']}: no answer ({llm.last_error})", file=sys.stderr)
            continue
        ref = "UNANSWERABLE (not in the sources)" if it.get("unanswerable") else it["answer"]
        j = llm.complete(JUDGE_SYS, f"Question: {it['question']}\nReference answer: {ref}\nCandidate answer: {a['text']}\n\n"
                                    f"Passages:\n{ctx}", 600, models=JUDGE_MODEL)
        try:
            grade = json.loads(re.search(r"\{.*\}", j["text"], re.S).group(0))
        except Exception:
            grade = dict(correct=None, faithful=None, why=f"grader reply not JSON: {(j or {}).get('text', llm.last_error)}"[:300])
        ref_nums = llm._nums(it["answer"]) if not it.get("unanswerable") else set()
        cache[it["id"]] = dict(answer=a["text"], correct=grade.get("correct"), faithful=grade.get("faithful"), why=grade.get("why"),
                               numbers_match=None if not ref_nums else ref_nums <= llm._nums(a["text"]),
                               unanswerable=bool(it.get("unanswerable")), ms=a["ms"],
                               tokens=a["input_tokens"] + a["output_tokens"] + (j["input_tokens"] + j["output_tokens"] if j else 0))
        path.write_text(json.dumps(cache, indent=1))
    return pd.DataFrame([dict(variant=v, id=k, **x) for k, x in cache.items()])


def answer_summary(a: pd.DataFrame) -> pd.DataFrame:
    out = []
    for v, g in a.groupby("variant", sort=False):
        ans, un = g[~g.unanswerable], g[g.unanswerable]
        out.append(dict(variant=v, correct=ans.correct.astype(float).mean(), faithful=g.faithful.astype(float).mean(),
                        numbers_match=ans.numbers_match.dropna().astype(float).mean(), refused_unanswerable=f"{int(un.correct.sum())}/{len(un)}",
                        answer_ms=round(g.ms.median()), tokens_per_q=round(g.tokens.mean())))
    return pd.DataFrame(out)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--variants", nargs="*", default=list(VARIANTS))
    ap.add_argument("--answers", nargs="*", default=[])
    args = ap.parse_args()
    OUT.mkdir(exist_ok=True)
    for ch in {VARIANTS[v]["chunks"] for v in args.variants}:
        corpus(ch)                                          # load / build indexes before timing
    search("warm up", "F", 5, dict(WINDOW, districts=[]))
    df, _ = run_retrieval(args.variants)
    df.to_csv(OUT / "rag_items.csv", index=False)
    summ = summarise(df)
    if args.answers:
        llm._load_env()
        ans = pd.concat([run_answers(v) for v in args.answers])
        ans.to_csv(OUT / "rag_answers.csv", index=False)
        summ = summ.merge(answer_summary(ans), on="variant", how="left")
    summ.to_csv(OUT / "rag_comparison.csv", index=False)
    (OUT / "rag_comparison.json").write_text(summ.to_json(orient="records", indent=1))
    pd.set_option("display.width", 220)
    print(summ.drop(columns=["label"]).round(3).to_string(index=False))
